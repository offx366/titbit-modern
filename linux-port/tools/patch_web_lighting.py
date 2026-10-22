"""Extend the pinned Emscripten legacy GL library with positional/spot lights.

The generated library retains Emscripten's MIT notice. User JS libraries are
loaded after built-ins, so this overrides the implementation without editing
the SDK or the Nix store. Fail explicitly when an SDK update changes a seam.
"""
from pathlib import Path


def build(source: Path, output: Path):
    text = source.read_text()
    # The built-in library already defines these macro helpers globally.
    begin = text.index('{{{')
    end = text.index('}}}', begin) + 3
    text = text[:begin] + text[end:]

    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError('Emscripten lighting seam changed: ' + old[:90])
        text = text.replace(old, new)

    # The engine enables the OpenGL default color-material mode:
    # FRONT_AND_BACK / AMBIENT_AND_DIFFUSE. Emscripten otherwise silently
    # ignores GL_COLOR_MATERIAL and lights every model with ambient 0.2.
    replace('    lightingEnabled: false,', '    lightingEnabled: false,\n    colorMaterialEnabled: false,')
    for enabled in ('true', 'false'):
        old = f'''        }} else if (cap == 0xB50 /* GL_LIGHTING */) {{
          if (GLEmulation.lightingEnabled != {enabled}) {{'''
        new = f'''        }} else if (cap == 0xB57 /* GL_COLOR_MATERIAL */) {{
          GLEmulation.colorMaterialEnabled = {enabled};
          GLImmediate.currentRenderer = null;
          return;
        }} else if (cap == 0xB50 /* GL_LIGHTING */) {{
          if (GLEmulation.lightingEnabled != {enabled}) {{'''
        replace(old, new)
    replace('''        } else if (cap == 0xB50 /* GL_LIGHTING */) {
          return GLEmulation.lightingEnabled ? 1 : 0;''', '''        } else if (cap == 0xB57 /* GL_COLOR_MATERIAL */) {
          return GLEmulation.colorMaterialEnabled ? 1 : 0;
        } else if (cap == 0xB50 /* GL_LIGHTING */) {
          return GLEmulation.lightingEnabled ? 1 : 0;''')
    replace("              vsLightingDefs += 'uniform vec4 u_materialAmbient;';", """              vsLightingDefs += 'uniform vec4 u_materialAmbient;';
              vsLightingDefs += 'uniform float u_colorMaterialEnabled;';""")
    replace("              vsLightingPass += '  vec3 ecNormal = normalize(u_normalMatrix * a_normal);';", """              vsLightingPass += '  vec4 materialAmbient = mix(u_materialAmbient, a_color, u_colorMaterialEnabled);';
              vsLightingPass += '  vec4 materialDiffuse = mix(u_materialDiffuse, a_color, u_colorMaterialEnabled);';
              vsLightingPass += '  vec3 ecNormal = normalize(u_normalMatrix * a_normal);';""")
    for old, new, count in [('u_materialAmbient.xyz', 'materialAmbient.xyz', 2),
                            ('u_materialDiffuse.xyz', 'materialDiffuse.xyz', 1),
                            ('u_materialDiffuse.w', 'materialDiffuse.w', 1)]:
        if text.count(old) != count:
            raise ValueError('Emscripten color-material seam changed: ' + old)
        text = text.replace(old, new)
    replace("          this.materialAmbientLocation = GLctx.getUniformLocation(this.program, 'u_materialAmbient');", """          this.materialAmbientLocation = GLctx.getUniformLocation(this.program, 'u_materialAmbient');
          this.colorMaterialLocation = GLctx.getUniformLocation(this.program, 'u_colorMaterialEnabled');""")
    replace('            if (this.materialAmbientLocation) GLctx.uniform4fv(this.materialAmbientLocation, GLEmulation.materialAmbient);', '''            if (this.materialAmbientLocation) GLctx.uniform4fv(this.materialAmbientLocation, GLEmulation.materialAmbient);
            if (this.colorMaterialLocation) GLctx.uniform1f(this.colorMaterialLocation, GLEmulation.colorMaterialEnabled ? 1 : 0);''')

    replace('    // TODO attenuation modes of lights', '''    lightSpotDirection: [],
    lightSpotCutoff: [],
    lightSpotExponent: [],
    lightAttenuation: [],''')
    replace('        GLEmulation.lightPosition[lightId] = new Float32Array([0.0, 0.0, 1.0, 0.0]);', '''        GLEmulation.lightPosition[lightId] = new Float32Array([0.0, 0.0, 1.0, 0.0]);
        GLEmulation.lightSpotDirection[lightId] = new Float32Array([0, 0, -1]);
        GLEmulation.lightSpotCutoff[lightId] = -1;
        GLEmulation.lightSpotExponent[lightId] = 0;
        GLEmulation.lightAttenuation[lightId] = new Float32Array([1, 0, 0]);''')
    replace("        abort('glLightfv: TODO: ' + pname);", '''        const value = HEAPF32[param >> 2];
        if (pname == 0x1204) { // GL_SPOT_DIRECTION, transformed like a normal
          const direction = [HEAPF32[param >> 2], HEAPF32[(param + 4) >> 2], HEAPF32[(param + 8) >> 2], 0];
          const normal = GLImmediate.matrixLib.mat4.create(GLImmediate.matrix[0]);
          GLImmediate.matrixLib.mat4.inverse(normal);
          GLImmediate.matrixLib.mat4.transpose(normal);
          GLImmediate.matrixLib.mat4.multiplyVec4(normal, direction);
          GLEmulation.lightSpotDirection[lightId].set(direction.slice(0, 3));
        } else if (pname == 0x1205) {
          GLEmulation.lightSpotExponent[lightId] = value;
        } else if (pname == 0x1206) {
          GLEmulation.lightSpotCutoff[lightId] = value == 180 ? -1 : Math.cos(value * Math.PI / 180);
        } else if (pname >= 0x1207 && pname <= 0x1209) {
          GLEmulation.lightAttenuation[lightId][pname - 0x1207] = value;
        } else abort('Unsupported light parameter: ' + pname);''')
    replace("                  vsLightingDefs += 'uniform vec4 u_lightPosition' + lightId + ';';", '''                  vsLightingDefs += 'uniform vec4 u_lightPosition' + lightId + ';';
                  vsLightingDefs += 'uniform vec3 u_lightAttenuation' + lightId + ';';
                  vsLightingDefs += 'uniform vec3 u_lightSpotDirection' + lightId + ';';
                  vsLightingDefs += 'uniform float u_lightSpotCutoff' + lightId + ';';
                  vsLightingDefs += 'uniform float u_lightSpotExponent' + lightId + ';';''')
    replace("                  vsLightingPass += '    vec3 lightDirection = normalize(u_lightPosition' + lightId + ').xyz;';", '''                  vsLightingPass += 'vec3 lightVector = u_lightPosition' + lightId + '.xyz - ecPosition.xyz * u_lightPosition' + lightId + '.w;';
                  vsLightingPass += 'float lightDistance = length(lightVector);';
                  vsLightingPass += 'vec3 lightDirection = lightVector / max(lightDistance, 0.0001);';
                  vsLightingPass += 'float attenuation = u_lightPosition' + lightId + '.w == 0.0 ? 1.0 : 1.0 / max(dot(u_lightAttenuation' + lightId + ', vec3(1.0, lightDistance, lightDistance * lightDistance)), 0.0001);';
                  vsLightingPass += 'if (u_lightSpotCutoff' + lightId + ' > -1.0) {';
                  vsLightingPass += 'float spotCos = dot(normalize(u_lightSpotDirection' + lightId + '), -lightDirection);';
                  vsLightingPass += 'attenuation *= spotCos >= u_lightSpotCutoff' + lightId + ' ? pow(max(spotCos, 0.0), u_lightSpotExponent' + lightId + ') : 0.0; }';''')
    replace("                  vsLightingPass += '    v_color.xyz += ambient + diffuse + specular;';",
            "                  vsLightingPass += '    v_color.xyz += attenuation * (ambient + diffuse + specular);';")
    replace('          this.lightPositionLocation = []', '''          this.lightPositionLocation = []
          this.lightAttenuationLocation = [];
          this.lightSpotDirectionLocation = [];
          this.lightSpotCutoffLocation = [];
          this.lightSpotExponentLocation = [];''')
    replace('            this.lightPositionLocation[lightId] = GLctx.getUniformLocation(this.program, `u_lightPosition${lightId}`);', '''            this.lightPositionLocation[lightId] = GLctx.getUniformLocation(this.program, `u_lightPosition${lightId}`);
            this.lightAttenuationLocation[lightId] = GLctx.getUniformLocation(this.program, `u_lightAttenuation${lightId}`);
            this.lightSpotDirectionLocation[lightId] = GLctx.getUniformLocation(this.program, `u_lightSpotDirection${lightId}`);
            this.lightSpotCutoffLocation[lightId] = GLctx.getUniformLocation(this.program, `u_lightSpotCutoff${lightId}`);
            this.lightSpotExponentLocation[lightId] = GLctx.getUniformLocation(this.program, `u_lightSpotExponent${lightId}`);''')
    replace('              if (this.lightPositionLocation[lightId]) GLctx.uniform4fv(this.lightPositionLocation[lightId], GLEmulation.lightPosition[lightId]);', '''              if (this.lightPositionLocation[lightId]) GLctx.uniform4fv(this.lightPositionLocation[lightId], GLEmulation.lightPosition[lightId]);
              if (this.lightAttenuationLocation[lightId]) GLctx.uniform3fv(this.lightAttenuationLocation[lightId], GLEmulation.lightAttenuation[lightId]);
              if (this.lightSpotDirectionLocation[lightId]) GLctx.uniform3fv(this.lightSpotDirectionLocation[lightId], GLEmulation.lightSpotDirection[lightId]);
              if (this.lightSpotCutoffLocation[lightId]) GLctx.uniform1f(this.lightSpotCutoffLocation[lightId], GLEmulation.lightSpotCutoff[lightId]);
              if (this.lightSpotExponentLocation[lightId]) GLctx.uniform1f(this.lightSpotExponentLocation[lightId], GLEmulation.lightSpotExponent[lightId]);''')
    output.write_text(text)
    return output
