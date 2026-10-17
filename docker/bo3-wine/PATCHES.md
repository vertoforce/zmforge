# The one file of Activision's that setup.sh modifies, and what their terms say

`setup.sh` reads one DLL out of your mod tools install, changes 22 bytes in a
copy of it, and writes that copy into the Wine prefix. Your install is not
written to. Nothing patched is distributed by us, because the patch is a
script that runs on your machine against your own file.

This is the sharpest edge in the whole setup, so the facts are below and the
call is yours.

## The file

`bin\avx\embree64r.dll`, 2,234,880 bytes, in the mod tools install. There is a
second copy at `bin\embree64r.dll`, 1,457,152 bytes, patched the same way.

It is Intel's Embree, a ray tracing library. The version string inside the
binary is `embree-2.3.3`. Radiant uses it for the lighting bake.

It is not Treyarch's code. The mod tools ship their own third-party licence
file, `modtools_license.txt`, and its `Embree` section is the **Apache License
2.0** in full, running from the section heading to the next component's. The
Intel Product License Agreement that appears later in the same file belongs to
`ISPCTextureCompressor`, not to Embree.

## What the patch changes

22 bytes, at file offsets `0x211F12` to `0x211F2A` in the `avx` copy. The
import name table entry:

```
before:  SetThreadIdealProcessorEx\0
after:   GetCurrentProcessId\0\0\0\0\0\0\0
```

That is the whole change. The string is overwritten in place and padded with
NUL bytes to its original length, so the import table keeps its layout and the
file keeps its size. No code is changed. No other byte moves.

### Why

Embree 2.3.3 sizes its task scheduler from `GetActiveProcessorCount`, the
host's logical CPU count. After creating each worker thread it pins that thread with
`SetThreadGroupAffinity` and `SetThreadIdealProcessorEx`, and throws if either
call fails. Wine's `SetThreadIdealProcessorEx` is a stub that returns `FALSE`
(`kernelbase/thread.c`, still a stub in Wine 11.17 master).
So Embree threw after its first worker, and every ray tracing phase ran one
thread against barriers sized for every logical CPU. A `winedbg` dump of a hung bake showed
exactly one Embree worker and one idle Radiant job thread per logical CPU. The scene build
took 18 to 103 s against 0.03 s on Windows. The probe bounces never finished.

`GetCurrentProcessId` ignores its arguments and never returns zero, so the
pinning call succeeds and Embree keeps creating threads. After the patch: one
Embree worker per logical CPU, scene build 0.13 to 0.23 s, `Export Done`.

The patch makes the library work under Wine. It does not remove a check, read
a secret, defeat protection or expose anything the tools do not already do.

## Where the patched copy goes

`scripts/patch-embree.py` takes a source directory and a destination:

```
patch-embree.py <your-tools-install> <prefix>/shims
```

It opens your file read-only and writes a new file under
`$ZMFORGE_WINE_PREFIX/shims/bin/avx/embree64r.dll`. The bake bind-mounts that
file read-only over the original inside the container. Your install keeps the
file Activision shipped.

`zmforge.toolchain.wine.WineRunner.ensure_shims` does the same thing for the
build chain. A DLL that does not contain the import exactly once is left
alone and not mounted.

The shim directory is gitignored, along with the whole Wine prefix, so no
patched binary is ever committed to this repository.

## What their terms say

Three documents govern, and they do not all point the same way. Each is
quoted from its published text.

**Activision's Program Utilities EULA**, Steam app 455130
(<https://store.steampowered.com/eula/455130_eula_0>):

> "You agree not to reverse engineer the Program Utilities, Third Party
> Materials, or New Game Materials with the exception of Qt..."

It names Third Party Materials alongside the Program Utilities, and carves out
only Qt. It does not use the word "modify" about the Program Utilities
themselves. The licence grant is to use the utilities "solely for your own
personal, non-commercial use in order to create the New Game Materials".

**The Apache License 2.0**, which the mod tools' own `modtools_license.txt`
applies to Embree, grants:

> "a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable
> copyright license to reproduce, prepare Derivative Works of, publicly
> display, publicly perform, sublicense, and distribute the Work and such
> Derivative Works in Source or Object form."

**The Steam Subscriber Agreement**
(<https://store.steampowered.com/subscriber_agreement/>), under which Steam
delivers the mod tools, says you may not:

> "reverse engineer, derive source code from, modify, disassemble, decompile,
> create derivative works based on [...] the Content and Services or any
> software accessed via Steam without the prior consent, in writing, of
> Valve".

So the file the patch touches carries a licence that grants the right to
prepare derivative works, and it is delivered through Steam, whose terms
restrict modifying software accessed via Steam, inside a package whose EULA
forbids reverse engineering Third Party Materials. Whether editing 22 bytes of
an import name table in your own copy is "reverse engineering" or a
modification Steam's terms reach, and which document controls when they
disagree, is **not settled here**. Running the patch is your call. This is not legal advice and
nobody involved is a lawyer.

What is settled, and is the reason the patch is shaped this way:

- No patched binary is in this repository, in the Docker image or in anything
  we would hand to anyone.
- The patch is a 64-line script, 24 lines of it code, that reads the user's
  own file on your own machine.
- Running it is the user's act, on the user's copy, under the user's licence.
- Skipping it costs the bake and nothing else. `--stages compile_full,link`
  builds a map with preview lighting and never touches the file.
