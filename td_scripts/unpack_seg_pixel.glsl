// Per-class mask decoder for the packed segmentation map (pixel shader).
//
// GLSL Multi TOP settings (build_seg_mask.py applies all of these):
//   GLSL page  : Mode = Pixel Shader, Output Type = 2D Texture, Vertex Shader = empty
//   Common page: Output Resolution = custom (any size; the shader resamples)
//   Vectors    : slot 0 uClasses = COCO ids per channel (R G B A), -1 = channel off
//                slot 1 uInRes   = me.inputs[0].width   me.inputs[0].height
//                slot 2 uOutRes  = me.par.resolutionw   me.par.resolutionh
//                slot 3 uEdge    = threshold (0..1), edge softness in output px (0 = raw alpha)
//
// Input 0: 32-bit float mono, per pixel  value = (classId + 1) + alpha * 0.99,  0 = background.
//
// Decode BEFORE filtering: the packed value mixes class (integer) and alpha (fraction), so
// filtering it directly invents phantom classes. Each of the 16 taps is unpacked, then only
// the alpha of the channel's own class is weighted (Catmull-Rom bicubic), then optionally
// re-thresholded with a screen-space width for a crisp anti-aliased edge.

uniform vec4 uClasses;
uniform vec2 uInRes;
uniform vec2 uOutRes;
uniform vec2 uEdge;

layout(location = 0) out vec4 fragColor;

// Catmull-Rom weights for offsets -1, 0, +1, +2 at fractional position t
vec4 cubicWeights(float t)
{
    float t2 = t * t, t3 = t2 * t;
    return vec4(
        -0.5*t3 +     t2 - 0.5*t,
         1.5*t3 - 2.5*t2 + 1.0,
        -1.5*t3 + 2.0*t2 + 0.5*t,
         0.5*t3 - 0.5*t2);
}

void main()
{
    vec2 inRes  = (uInRes.x  > 0.5) ? uInRes  : vec2(160.0);
    vec2 outRes = (uOutRes.x > 0.5) ? uOutRes : vec2(640.0);

    // Position from the rasteriser (gl_FragCoord), not from the vertex stage.
    vec2 uv    = gl_FragCoord.xy / outRes;
    vec2 inPos = clamp(uv, 0.0, 1.0) * inRes - 0.5;
    ivec2 tl   = ivec2(floor(inPos));
    vec2  f    = fract(inPos);

    vec4 wx = cubicWeights(f.x);
    vec4 wy = cubicWeights(f.y);
    ivec2 maxTexel = ivec2(inRes) - 1;
    ivec4 wanted   = ivec4(floor(uClasses + 0.5));

    vec4 acc = vec4(0.0);
    for (int j = 0; j < 4; j++)
    {
        for (int i = 0; i < 4; i++)
        {
            ivec2 c = clamp(tl + ivec2(i - 1, j - 1), ivec2(0), maxTexel);
            float v = texelFetch(sTD2DInputs[0], c, 0).r;

            int   id = int(floor(v)) - 1;                 // background (0.0) -> -1, never matches
            float a  = min(fract(v) / 0.99, 1.0);         // guard float32 rounding above 0.99
            float w  = wx[i] * wy[j];

            acc += w * vec4(equal(ivec4(id), wanted)) * a;
        }
    }
    vec4 outA = clamp(acc, 0.0, 1.0);                     // Catmull-Rom can overshoot slightly

    // Optional crisp anti-aliased edge, width uEdge.y output pixels around threshold uEdge.x
    if (uEdge.y > 0.0)
    {
        float texelsPerPixel = inRes.x / outRes.x;
        float halfWidth      = 0.5 * uEdge.y * texelsPerPixel;
        outA = smoothstep(uEdge.x - halfWidth, uEdge.x + halfWidth, outA);
    }

    fragColor = TDOutputSwizzle(outA);
}
