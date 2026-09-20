// Per-class mask decoder for the packed segmentation map -> 2D Texture Array.
//
// Input 0 : segmentation_data (32-bit float, 160x160). Per pixel:
//           value = (classId + 1) + alpha * 0.99,  0.0 = background
// Output  : GLSL TOP, Output Type = 2D Texture Array, Depth = number of classes
//           you want (80 for full COCO). Layer i == COCO class i.
//           Output Access = Write Only. Output Resolution on the Common page is
//           the mask size you want (e.g. 640x640); the shader resamples.
//
// Why decode before interpolating: the packed value mixes class (integer part)
// and alpha (fraction). Filtering 1.9 (person) against 3.9 (car) gives 2.9,
// a phantom class. Every neighbour is unpacked first, then only alphas of the
// layer's own class are blended.

layout (local_size_x = 8, local_size_y = 8) in;
void main()
{
    ivec2 coord   = ivec2(gl_GlobalInvocationID.xy);
    ivec3 outSize = imageSize(mTDComputeOutputs[0]);     // ivec3 because the output is an array
    if (coord.x >= outSize.x || coord.y >= outSize.y) return;

    // Output pixel centre -> input texel space.
    // Do NOT use uTD2DInfos[0].res here: in compute mode it has been observed
    // reporting the output size, which shrinks the mask into the bottom-left
    // corner. textureSize asks the bound texture directly.
    vec2 inRes  = vec2(textureSize(sTD2DInputs[0], 0));
    vec2 outRes = vec2(outSize.xy);
    vec2 uv     = (vec2(coord) + 0.5) / outRes;
    vec2 inPos  = uv * inRes - 0.5;

    ivec2 tl = ivec2(floor(inPos));
    vec2  f  = fract(inPos);
    f = f * f * (3.0 - 2.0 * f);                          // smoothstep weights: softer edges

    ivec2 maxTexel = ivec2(inRes) - 1;
    float v00 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(0, 0), ivec2(0), maxTexel), 0).r;
    float v10 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(1, 0), ivec2(0), maxTexel), 0).r;
    float v01 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(0, 1), ivec2(0), maxTexel), 0).r;
    float v11 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(1, 1), ivec2(0), maxTexel), 0).r;

    // Unpack each neighbour. Background (0.0) decodes to id -1, never matches a layer.
    // min(.., 1.0) guards against fract() landing a hair above 0.99 after float32 rounding.
    int   id00 = int(floor(v00)) - 1;  float a00 = min(fract(v00) / 0.99, 1.0);
    int   id10 = int(floor(v10)) - 1;  float a10 = min(fract(v10) / 0.99, 1.0);
    int   id01 = int(floor(v01)) - 1;  float a01 = min(fract(v01) / 0.99, 1.0);
    int   id11 = int(floor(v11)) - 1;  float a11 = min(fract(v11) / 0.99, 1.0);

    // Fast path: all four neighbours are background -> every layer is 0 here.
    // The array is not cleared between frames, so the zeros must still be written.
    if (id00 < 0 && id10 < 0 && id01 < 0 && id11 < 0)
    {
        for (int i = 0; i < outSize.z; i++)
            imageStore(mTDComputeOutputs[0], ivec3(coord, i), TDOutputSwizzle(vec4(0.0)));
        return;
    }

    for (int i = 0; i < outSize.z; i++)
    {
        // Keep only this layer's class, then interpolate the alphas
        float alpha00 = (id00 == i) ? a00 : 0.0;
        float alpha10 = (id10 == i) ? a10 : 0.0;
        float alpha01 = (id01 == i) ? a01 : 0.0;
        float alpha11 = (id11 == i) ? a11 : 0.0;

        float top        = mix(alpha00, alpha10, f.x);
        float bot        = mix(alpha01, alpha11, f.x);
        float finalAlpha = mix(top, bot, f.y);

        // Optional: tighten edges if the blend feels too soft
        // finalAlpha = smoothstep(0.05, 0.95, finalAlpha);

        imageStore(mTDComputeOutputs[0], ivec3(coord, i), TDOutputSwizzle(vec4(finalAlpha)));
    }
}
