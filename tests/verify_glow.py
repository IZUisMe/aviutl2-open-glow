"""Run OpenGlow's Lua with AviUtl2's LuaJIT and compile its HLSL on Windows.

Usage: python tests/verify_glow.py [path/to/luaJIT.dll]
This checks allocation planning and coordinate coverage; it does not render AviUtl2.
"""
import ctypes as C
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "OpenGlow.anm2").read_text(encoding="utf-8")


def check_lua():
    lua = C.CDLL(sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files\AviUtl2\luaJIT.dll")
    lua.luaL_newstate.restype = C.c_void_p
    lua.luaL_openlibs.argtypes = [C.c_void_p]
    lua.luaL_loadstring.argtypes = [C.c_void_p, C.c_char_p]
    lua.lua_pcall.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int]
    lua.lua_tolstring.argtypes = [C.c_void_p, C.c_int, C.c_void_p]
    lua.lua_tolstring.restype = C.c_char_p
    lua.lua_close.argtypes = [C.c_void_p]
    state = lua.luaL_newstate()
    lua.luaL_openlibs(state)
    harness = r'''
local source = SOURCE
local run = assert(loadstring(source))
local cases = 0
local function check(w, h, asp, ang, rad, fixed, filter)
    strength, radius, falloff, threshold, gamma_v = 100, rad, 2, 0, 2.2
    aspect, angle, blend_mode = asp, ang, 0
    dither, mono_dither, fixsize, tint = true, false, fixed, nil
    local buffers, peak, pre, final = {}, 0
    local function dots()
        local n = 0
        for _, size in pairs(buffers) do n = n + size[1] * size[2] end
        return n
    end
    obj = { w = w, h = h, frame = 1 }
    obj.getinfo = function(key)
        if key == "image_max" then return 16384, 16384 end
        if key == "filter" then return filter end
        error(key)
    end
    obj.effect = function(name, _, top, _, bottom, _, left, _, right)
        assert(not fixed and not filter)
        obj.w, obj.h = obj.w + left + right, obj.h + top + bottom
    end
    obj.clearbuffer = function(name, bw, bh)
        assert(bw >= 1 and bh >= 1 and bw <= 16384 and bh <= 16384)
        buffers[name] = {bw, bh}
        peak = math.max(peak, dots())
        assert(dots() <= 14000000, "cache allocations exceed budget")
    end
    obj.pixelshader = function(name, target, resources, constants)
        if name == "OG_Pre" then pre = constants end
        if name == "OG_Final" then final = constants end
        if type(resources) == "string" then resources = {resources} end
        for _, resource in ipairs(resources) do
            assert(resource == "object" or buffers[resource], "missing source buffer")
            if resource == target and target ~= "object" then
                peak = math.max(peak, dots() + buffers[target][1] * buffers[target][2])
                assert(peak <= 14000000, "shader duplicate exceeds budget")
            end
        end
    end
    run()
    if not final then assert(math.max(w, h) <= 2); return end
    assert(pre and final)
    local gw, gh = final[19], final[20]
    local a, b, c, d = pre[9], pre[10], pre[11], pre[12]
    local ia, ib, ic, id = final[5], final[6], final[7], final[8]
    -- Every source corner must fit inside the glow texture, including rotation.
    for _, x in ipairs({-obj.w / 2, 0, obj.w / 2}) do
        for _, y in ipairs({-obj.h / 2, 0, obj.h / 2}) do
            local gx, gy = ia * x + ib * y, ic * x + id * y
            assert(math.abs(gx) <= gw / 2 + 1e-6, "horizontal crop")
            assert(math.abs(gy) <= gh / 2 + 1e-6, "vertical crop")
            assert(math.abs(a * gx + b * gy - x) < 1e-6, "pre/final X mismatch")
            assert(math.abs(c * gx + d * gy - y) < 1e-6, "pre/final Y mismatch")
        end
    end
    assert(pre[4] >= 1 and pre[23] >= 1)
    for _, size in pairs(buffers) do assert(size[1] == 1 and size[2] == 1) end
    if w == 2048 and h == 1474 and fixed and asp == 0 then
        assert(gw == w and gh == h, "small images must keep full resolution")
    end
    cases = cases + 1
end
for _, wh in ipairs({{1,1}, {2,2}, {17,9}, {2048,1474}, {3840,2160},
                     {6251,4501}, {16384,16384}, {16384,1}, {1,16384}}) do
    for _, asp in ipairs({-10, -3, 0, 3, 10}) do
        for _, ang in ipairs({0, 45, 89, 137}) do
            for _, rad in ipairs({4, 300, 2000}) do
                check(wh[1], wh[2], asp, ang, rad, true, false)
            end
        end
    end
end
check(6251, 4501, 0, 0, 300, false, false)
check(6251, 4501, 3, 45, 300, false, true)
print("Lua allocation/coverage checks passed: " .. cases .. " cases")
'''
    code = harness.replace("local source = SOURCE", "local source = [====[" + SOURCE + "]====]")
    try:
        result = lua.luaL_loadstring(state, code.encode("utf-8"))
        if result == 0:
            result = lua.lua_pcall(state, 0, 0, 0)
        if result:
            raise RuntimeError(lua.lua_tolstring(state, -1, None).decode("utf-8"))
    finally:
        lua.lua_close(state)


def check_shaders():
    compiler = C.WinDLL("d3dcompiler_47.dll")
    compiler.D3DCompile.argtypes = [C.c_void_p, C.c_size_t, C.c_char_p, C.c_void_p,
                                  C.c_void_p, C.c_char_p, C.c_char_p, C.c_uint,
                                  C.c_uint, C.POINTER(C.c_void_p), C.POINTER(C.c_void_p)]
    compiler.D3DCompile.restype = C.c_long

    def method(blob, index, result, *args):
        table = C.cast(blob, C.POINTER(C.POINTER(C.c_void_p))).contents
        return C.WINFUNCTYPE(result, C.c_void_p, *args)(table[index])

    for name, shader in re.findall(r"--\[\[pixelshader@(\w+):(.*?)\]\]", SOURCE, re.S):
        data = shader.encode("utf-8")
        blob, errors = C.c_void_p(), C.c_void_p()
        result = compiler.D3DCompile(data, len(data), None, None, None, name.encode(),
                                    b"ps_5_0", 1 << 11, 0, C.byref(blob), C.byref(errors))
        try:
            if result < 0:
                message = method(errors, 3, C.c_void_p)(errors)
                raise RuntimeError(C.string_at(message).decode("utf-8"))
            print(f"HLSL compiled: {name}")
        finally:
            for item in (blob, errors):
                if item:
                    method(item, 2, C.c_ulong)(item)


if __name__ == "__main__":
    check_lua()
    check_shaders()
