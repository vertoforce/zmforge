# Setting this up against your own mod tools install

This builds a Black Ops III map on Linux: compile, lighting bake and link, no
Windows machine anywhere. It needs your own copy of the Black Ops III mod
tools. None of Activision's files are in this repository or in the image it
builds, and none ever will be.

Three commands, once:

```
cp bo3-wine.env.example bo3-wine.env      # set ZMFORGE_WINE_TOOLS to your install
./setup.sh                                # image, Wine prefix, ray-tracer shim
./check.sh                                # says what is still missing, in English
```

Then a map:

```
cd ../..                   # the zmforge checkout, two levels up
ZMFORGE_WINE_TOOLS=/path/to/your/modtools \
  .venv/bin/zmforge build zm_your_map
```

A warm build of `zm_forge_gate` takes about 86 s with the versions listed below: compile 5.8 s,
bake 52.2 s, link 28.3 s.

## What you have to supply

- **The mod tools.** Steam app 455130, "Call of Duty: Black Ops III Mod
  Tools", free to anyone who owns the game. The folder whose name ends in
  `455130`, holding `bin/`, `share/`, `map_source/`, `deffiles/` and
  `source_data/`. A full install is about 28 GB.
- **An NVIDIA GPU and its driver, for the bake only.** The bake is the one
  stage that needs a display and a real GPU. Compile and link do not: run
  `--stages compile_full,link` on a machine without one.
- **`nvidia-container-toolkit`**, so `docker run --gpus all` works.
- **Docker.** There is no host-Wine path. Everything runs in the image.
- **About 12 GB free.** The Wine prefix plus Radiant's converted-asset cache
  comes to about 1.5 GB. Every stage also writes into your tools install:
  `cod2map64` into `share/raw`, the linker into `usermaps/<map>/zone`. The
  tools root has to be writable.

`./check.sh` tests each of these and names the ones that fail. It exits 0 when
a full build can run, 2 when only the bake is out of reach, and 1 when nothing
will run.

## Versions to match

The timings and fixes here were measured with these versions:

| | |
|---|---|
| Wine | 11.0 stable, from WineHQ |
| DXVK | 3.1.1 |
| Mod tools | Steam app 455130, buildid 5284267 |

Other Wine versions, GPU vendors and tools builds are untested. Treat the
timings as a guide, not a promise.

## What does not work

- **Playing the map.** No map built in this image has been loaded in the game. The
  game is not in this image and the map is not installed into it. Whether a
  map built in this image plays correctly is **unverified**.
- **`gdtdb.exe /update`**, the asset-database refresh. It exits 53 and prints
  nothing. It is a .NET Framework 4.5 program and the image has no Mono. Skip
  that stage.
- **Byte-identical output.** The BSP a compile under Wine writes differs from
  the same map compiled on Windows. On `zm_forge_gate`, 3 of 25 lumps and 152
  bytes. Two compiles under Wine agree with each other, so the difference is
  systematic, and its cause is **unknown**.
- **An AMD or Intel GPU.** Untested. The bake needs Vulkan for DXVK and a real
  GLX for Xorg, which those drivers have, so it may work. Nobody has run it.
- **Wine other than 11.0.** The embree shim exists because Wine stubs
  `SetThreadIdealProcessorEx`. That stub is still there in Wine 11.17 master.
  A Wine that implements it would make the shim
  unnecessary and harmless.

## When something fails

`./check.sh` first. It converts the failures that otherwise surface deep
inside Wine:

| What you would have seen | What it means |
|---|---|
| `unimplemented function msvcr110.dll.??0_TaskCollection@details@Concurrency@@QEAA@XZ, aborting` | Microsoft's VC++ 2012 runtime is not in the prefix. Re-run `./setup.sh`. |
| The bake runs at 400% CPU for ten minutes with no output | The embree shim is not applied. `./check.sh` says whether the patch matched your DLL. |
| The bake logs hundreds of `program object is not successfully linked` | It is on llvmpipe, not the GPU. `NVIDIA_DRIVER_CAPABILITIES` has to include `graphics`. |
| `wine: Unhandled page fault` during a bake | `GdtDBTrayLauncher.exe` started. The blank shim covers it, and `./setup.sh` writes that shim. |
| The linker names an asset in an `ERROR:` line | Your tools copy does not carry that file. The error is the shopping list. |

Stage logs land in `zmforge-logs/<map>/`. Radiant's own log is appended to the
bake log after a `== Radiant.log` marker, and it is the only record of the
bake's phases.

## Licensing

In short: `setup.sh` patches one import in a copy of your own tools' Embree
DLL, an Apache-2.0 library. Steam's Subscriber Agreement restricts modifying
software accessed via Steam without Valve's written consent, so running it is
your call. Without it, compile and link still work; build on Windows if you
would rather not.

Read `PATCHES.md` before running `setup.sh`. It describes the one thing here
that modifies a file Activision shipped, exactly what it changes, and what
their terms say about modification. `../../docs/licensing.md` has the
quoted clauses.
