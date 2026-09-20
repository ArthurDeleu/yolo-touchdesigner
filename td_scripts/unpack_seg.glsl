// Single-class mask decoder for the packed segmentation map.
//
// Input 0 : segmentation_data (32-bit float, 160x160). Per pixel:
//           value = (classId + 1) + alpha * 0.99,  0.0 = background
// Output  : plain 2D texture (GLSL TOP: Output Type = 2D Texture, Output Access
//           = Write Only). Set Output Resolution on the Common page to whatever
//           size you want the mask at (e.g. 640x640); the shader resamples.
// Uniform : uClass (Vectors page, slot 0, x component) = COCO index of the class to extract.
//           0 = person, 2 = car, 15 = cat, 16 = dog, ...
//
// Why decode before interpolating: the packed value mixes class (integer part)
// and alpha (fraction). Filtering 1.9 (person) against 3.9 (car) gives 2.9,
// a phantom class. So every neighbour is unpacked first, and only the alphas
// of the requested class are blended.

uniform float uClass;   // TD's Vectors page declares floats; cast below

layout (local_size_x = 8, local_size_y = 8) in;
void main()
{
    ivec2 coord   = ivec2(gl_GlobalInvocationID.xy);
    ivec2 outSize = imageSize(mTDComputeOutputs[0]);
    if (coord.x >= outSize.x || coord.y >= outSize.y) return;

    // Output pixel centre -> input texel space
    // Ask the texture itself for its size; do not trust uTD2DInfos here, it has
    // been observed reporting the output size and collapsing the mask into the
    // bottom-left corner.
    vec2 inRes  = vec2(textureSize(sTD2DInputs[0], 0));
    vec2 outRes = vec2(outSize);
    vec2 uv     = (vec2(coord) + 0.5) / outRes;
    vec2 inPos  = uv * inRes - 0.5;

    ivec2 tl = ivec2(floor(inPos));
    vec2  f  = fract(inPos);
    f = f * f * (3.0 - 2.0 * f);                // smoothstep weights: softer edges

    ivec2 maxTexel = ivec2(inRes) - 1;
    float v00 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(0, 0), ivec2(0), maxTexel), 0).r;
    float v10 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(1, 0), ivec2(0), maxTexel), 0).r;
    float v01 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(0, 1), ivec2(0), maxTexel), 0).r;
    float v11 = texelFetch(sTD2DInputs[0], clamp(tl + ivec2(1, 1), ivec2(0), maxTexel), 0).r;

    // Unpack each neighbour: class id and alpha
    int   id00 = int(floor(v00)) - 1;  float a00 = fract(v00) / 0.99;
    int   id10 = int(floor(v10)) - 1;  float a10 = fract(v10) / 0.99;
    int   id01 = int(floor(v01)) - 1;  float a01 = fract(v01) / 0.99;
    int   id11 = int(floor(v11)) - 1;  float a11 = fract(v11) / 0.99;

    // Keep only the requested class, then interpolate the alphas
    int wanted = int(uClass + 0.5);
    float alpha00 = (id00 == wanted) ? a00 : 0.0;
    float alpha10 = (id10 == wanted) ? a10 : 0.0;
    float alpha01 = (id01 == wanted) ? a01 : 0.0;
    float alpha11 = (id11 == wanted) ? a11 : 0.0;

    float top        = mix(alpha00, alpha10, f.x);
    float bot        = mix(alpha01, alpha11, f.x);
    float finalAlpha = mix(top, bot, f.y);

    imageStore(mTDComputeOutputs[0], coord, TDOutputSwizzle(vec4(finalAlpha)));
}
