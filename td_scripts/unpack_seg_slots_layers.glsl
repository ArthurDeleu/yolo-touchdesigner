// Per-person mask decoder -> 2D Texture Array, one layer per slot (compute shader).
//
// Input 0 : segmentation_data (32-bit float mono). Per pixel value = (id + 1) + alpha*0.99,
//           0.0 = background. id is the page's tracked instance id (>= 100).
// Uniforms: uSlotsA = ids in slots 0-3, uSlotsB = ids in slots 4-7 (-1 = empty slot),
//           driven from the instance_slots Script CHOP. uEdge = (threshold, softness 0..1).
// Output  : GLSL TOP, Mode = Compute, Output Type = 2D Texture Array, Depth = 8,
//           Output Access = Write Only. Layer k == the person occupying slot k.
//
// Downstream: a Geometry COMP with 8 instances and this TOP as instance texture,
// texture index = slot, shows one person per instance. In GLSL, sample with
// texture(sTD2DArrayInputs[0], vec3(uv, layer)).
//
// Derived from unpack_seg_layers.glsl (Sep 14): same decode-then-filter rule, so two
// touching bodies never blend into a phantom id; only the selector changed.

uniform vec4 uSlotsA;
uniform vec4 uSlotsB;
uniform vec2 uEdge;

layout (local_size_x = 8, local_size_y = 8) in;

int slotId(int k)
{
    vec4 v = (k < 4) ? uSlotsA : uSlotsB;
    int  c = k & 3;
    return int(floor((c == 0 ? v.x : c == 1 ? v.y : c == 2 ? v.z : v.w) + 0.5));
}

void main()
{
    ivec2 coord   = ivec2(gl_GlobalInvocationID.xy);
    ivec3 outSize = imageSize(mTDComputeOutputs[0]);
    if (coord.x >= outSize.x || coord.y >= outSize.y) return;

    vec2 inRes  = vec2(textureSize(sTD2DInputs[0], 0));   // ask the texture, not uTD2DInfos (see Sep 14 note)
    vec2 outRes = vec2(outSize.xy);
    vec2 uv     = (vec2(coord) + 0.5) / outRes;
    vec2 inPos  = uv * inRes - 0.5;

    ivec2 tl = ivec2(floor(inPos));
    vec2  f  = fract(inPos);
    f = f * f * (3.0 - 2.0 * f);

    ivec2 maxTexel = ivec2(inRes) - 1;
    float v00 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(0, 0), ivec2(0), maxTexel), 0).r;
    float v10 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(1, 0), ivec2(0), maxTexel), 0).r;
    float v01 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(0, 1), ivec2(0), maxTexel), 0).r;
    float v11 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(1, 1), ivec2(0), maxTexel), 0).r;

    int   id00 = int(floor(v00)) - 1;  float a00 = min(fract(v00) / 0.99, 1.0);
    int   id10 = int(floor(v10)) - 1;  float a10 = min(fract(v10) / 0.99, 1.0);
    int   id01 = int(floor(v01)) - 1;  float a01 = min(fract(v01) / 0.99, 1.0);
    int   id11 = int(floor(v11)) - 1;  float a11 = min(fract(v11) / 0.99, 1.0);

    bool empty = (id00 < 0 && id10 < 0 && id01 < 0 && id11 < 0);

    for (int k = 0; k < outSize.z; k++)
    {
        float a = 0.0;
        int wanted = slotId(k);
        if (!empty && wanted >= 0)
        {
            float top = mix((id00 == wanted) ? a00 : 0.0, (id10 == wanted) ? a10 : 0.0, f.x);
            float bot = mix((id01 == wanted) ? a01 : 0.0, (id11 == wanted) ? a11 : 0.0, f.x);
            a = mix(top, bot, f.y);
            if (uEdge.y > 0.0)
            {
                float hw = 0.5 * uEdge.y;
                a = smoothstep(uEdge.x - hw, uEdge.x + hw, a);
            }
        }
        // The array is not cleared between frames: zeros must be written too.
        imageStore(mTDComputeOutputs[0], ivec3(coord, k), TDOutputSwizzle(vec4(a)));
    }
}
