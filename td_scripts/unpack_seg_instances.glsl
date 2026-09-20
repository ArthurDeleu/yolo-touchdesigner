// Per-instance colour decoder for the packed segmentation map (pixel shader).
//
// Pairs with SEG_PACK_MODE = "instance" in the web app: the integer part of each
// texel is a tracked instance id (stable per body across frames), the fraction
// is that body's mask alpha. Every id gets its own hue, so N people = N colours
// with no cap on N. For the legacy per-class RGBA split use unpack_seg_pixel.glsl.
//
// GLSL Multi TOP settings (build_seg_mask.py applies all of these):
//   GLSL page  : Mode = Pixel Shader, Output Type = 2D Texture, Vertex Shader = empty
//   Common page: Output Resolution = custom (any size; the shader resamples)
//   Vectors    : slot 0 uInRes   = me.inputs[0].width   me.inputs[0].height
//                slot 1 uOutRes  = me.par.resolutionw   me.par.resolutionh
//                slot 2 uEdge    = threshold (0..1), edge softness in output px (0 = raw alpha)
//                slot 3 uPalette = hue offset (0..1), saturation, value, hue step (0 = golden ratio)
//
// Input 0: 32-bit float mono, per pixel  value = (id + 1) + alpha * 0.99,  0 = background.
// Output : premultiplied RGBA. A = mask alpha, RGB = that body's colour * A.
//
// Filtering happens on the *decoded* taps, not on the packed value: id and alpha
// are unpacked per tap, each tap contributes its own colour weighted by its alpha,
// and the result is normalised. Two bodies touching therefore blend hue across
// the seam instead of inventing a third id (which filtering the packed float would do).

uniform vec2 uInRes;
uniform vec2 uOutRes;
uniform vec2 uEdge;
uniform vec4 uPalette;

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

vec3 hsv2rgb(vec3 c)
{
    vec3 p = abs(fract(c.xxx + vec3(0.0, 2.0/3.0, 1.0/3.0)) * 6.0 - 3.0);
    return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

// Golden-ratio hue spacing: consecutive ids land far apart on the wheel and
// the sequence never repeats exactly, so neighbours stay distinguishable.
vec3 idColour(int id)
{
    float step = (uPalette.w > 0.0) ? uPalette.w : 0.61803398875;
    float hue  = fract(uPalette.x + float(id) * step);
    float sat  = (uPalette.y > 0.0) ? uPalette.y : 0.85;
    float val  = (uPalette.z > 0.0) ? uPalette.z : 1.0;
    return hsv2rgb(vec3(hue, sat, val));
}

void main()
{
    vec2 inRes  = (uInRes.x  > 0.5) ? uInRes  : vec2(160.0);
    vec2 outRes = (uOutRes.x > 0.5) ? uOutRes : vec2(640.0);

    vec2 uv    = gl_FragCoord.xy / outRes;
    vec2 inPos = clamp(uv, 0.0, 1.0) * inRes - 0.5;
    ivec2 tl   = ivec2(floor(inPos));
    vec2  f    = fract(inPos);

    vec4 wx = cubicWeights(f.x);
    vec4 wy = cubicWeights(f.y);
    ivec2 maxTexel = ivec2(inRes) - 1;

    vec3  accRGB = vec3(0.0);
    float accA   = 0.0;
    for (int j = 0; j < 4; j++)
    {
        for (int i = 0; i < 4; i++)
        {
            ivec2 c = clamp(tl + ivec2(i - 1, j - 1), ivec2(0), maxTexel);
            float v = texelFetch(sTD2DInputs[0], c, 0).r;

            int   id = int(floor(v)) - 1;                 // background (0.0) -> -1
            float a  = min(fract(v) / 0.99, 1.0);         // guard float32 rounding above 0.99
            float w  = wx[i] * wy[j] * a * float(id >= 0);

            accRGB += w * idColour(id);
            accA   += w;
        }
    }

    float outA = clamp(accA, 0.0, 1.0);                   // Catmull-Rom can overshoot slightly
    vec3  rgb  = (accA > 1e-5) ? accRGB / accA : vec3(0.0);

    // Optional crisp anti-aliased edge, width uEdge.y output pixels around threshold uEdge.x
    if (uEdge.y > 0.0)
    {
        float texelsPerPixel = inRes.x / outRes.x;
        float halfWidth      = 0.5 * uEdge.y * texelsPerPixel;
        outA = smoothstep(uEdge.x - halfWidth, uEdge.x + halfWidth, outA);
    }

    fragColor = TDOutputSwizzle(vec4(rgb * outA, outA));
}
