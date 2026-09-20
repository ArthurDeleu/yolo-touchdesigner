// Pulls one layer out of the seg_layers 2D texture array as a plain mono TOP.
// Input 0 = seg_layers. Vectors: uLayer = slot index (0..7). Duplicate the TOP and
// change uLayer for each person you want as a separate mask.
uniform float uLayer;
layout(location = 0) out vec4 fragColor;
void main()
{
    float a = texture(sTD2DArrayInputs[0], vec3(vUV.st, uLayer)).r;
    fragColor = TDOutputSwizzle(vec4(a));
}
