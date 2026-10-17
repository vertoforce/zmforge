# Wine, 64-bit, just enough to run the Black Ops III mod tools head-less.
#
# WHY WineHQ and not Debian's own wine: the mod tools are MSVC-built 64-bit
# console programs that call into a wide slice of Win32; the newer the Wine,
# the fewer of those calls are stubs. Debian bookworm ships wine 8.0.
#
# The tools themselves are NOT in this image. They are bind-mounted at
# /tools (see docker-compose.yml) and are the user's own Steam install,
# copied for their own use: never baked into an image, never published.
FROM debian:bookworm-slim@sha256:88200866dfff7ea7f5cbcb6ec7c8a701889efe6fe859fe64d6990e4b07ea4171

ARG WINE_BRANCH=stable

RUN set -eux; \
    dpkg --add-architecture i386; \
    # winetricks lives in contrib, which the slim base does not enable.
    echo "deb http://deb.debian.org/debian bookworm main contrib" \
        > /etc/apt/sources.list.d/contrib.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates wget gnupg; \
    mkdir -p /etc/apt/keyrings; \
    wget -qO /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key; \
    echo "deb [signed-by=/etc/apt/keyrings/winehq-archive.key] https://dl.winehq.org/wine-builds/debian/ bookworm main" \
        > /etc/apt/sources.list.d/winehq.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends "winehq-${WINE_BRANCH}" \
        xvfb xauth cabextract procps p7zip-full python3 winbind \
        winetricks unzip \
        # The lighting bake needs a display with real GLX; Xvfb only has
        # llvmpipe. xserver-xorg-core plus the nvidia driver the container
        # runtime injects gives Xorg on the GPU (see with-display.sh).
        xserver-xorg-core \
        # The lighting baker is a Qt application that loads d3d11 through
        # ANGLE and wined3d, so it needs a GL stack. libglvnd plus the
        # NVIDIA libraries the container runtime injects gives it the real
        # GPU; mesa is the software fallback. mesa-utils is here for
        # glxinfo, which is the only way to check which one is in use.
        libgl1 libglx0 libegl1 libvulkan1 mesa-utils \
        libgl1-mesa-dri; \
    rm -rf /var/lib/apt/lists/*

# A 64-bit-only prefix. The tools are all cod2map64/linker_modtools 64-bit
# binaries, and a win64 prefix avoids pulling the 32-bit loader in at all.
# Harmless without --gpus, and required with it: the container runtime reads
# these to decide which driver libraries to inject.
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics,display

ENV WINEARCH=win64 \
    WINEPREFIX=/wineprefix \
    WINEDEBUG=-all \
    # mscoree=d: nothing here is .NET, so do not offer to install Mono.
    # msvcr110,msvcp110=n: use Microsoft's own VC++ 2012 runtime, which the
    # entrypoint installs into the prefix. Wine's builtin msvcr110 has no
    # Concurrency Runtime task scheduler and linker_modtools.exe aborts on
    # ??0_TaskCollection@details@Concurrency@@QEAA@XZ before printing a line
    # [measured]. Installing the DLLs is not enough on its own:
    # without this override Wine still loads its builtin and still aborts.
    WINEDLLOVERRIDES="mscoree=d;msvcr110,msvcp110=n" \
    PATH=/opt/wine-stable/bin:/usr/lib/wine:$PATH

# DXVK: D3D11 over Vulkan, for the lighting bake only. Radiant's probe pass
# renders through D3D11. Through wined3d (Wine's own D3D11 on OpenGL) the
# NVIDIA GLSL compiler spent ~60 s linking the translated probe compute
# shader and then still reported "program object is not successfully
# linked" and "No active compute shader" on the dispatches [measured, 305 + 30 lines]. Through DXVK the same bake logged no D3D
# error and finished in 17 s against 88 s (Windows: 12 s). The
# entrypoint copies the three DLLs into the prefix's system32; they are only
# used when a stage's WINEDLLOVERRIDES says d3d11,dxgi,d3d10core=n, which
# the bake's does and the compile's and link's do not.
ARG DXVK_VERSION=3.1.1
ARG DXVK_SHA256=40565b4a724aadc4433fa4e010b4b23916d9b1f1baeee64e17186db94f54e608
RUN set -eux; \
    wget -qO /tmp/dxvk.tar.gz \
        "https://github.com/doitsujin/dxvk/releases/download/v${DXVK_VERSION}/dxvk-${DXVK_VERSION}.tar.gz"; \
    echo "${DXVK_SHA256}  /tmp/dxvk.tar.gz" | sha256sum -c -; \
    mkdir -p /opt/dxvk; \
    tar -xzf /tmp/dxvk.tar.gz -C /opt/dxvk --strip-components=1 "dxvk-${DXVK_VERSION}/x64"; \
    rm /tmp/dxvk.tar.gz; \
    ls /opt/dxvk/x64/d3d11.dll /opt/dxvk/x64/dxgi.dll /opt/dxvk/x64/d3d10core.dll

# winetricks decides a 64-bit prefix is driven by a binary called wine64,
# which Wine 10+ no longer ships (there is one loader now). Without this
# symlink every winetricks verb dies on "wine cmd.exe /c echo '%AppData%'
# returned empty string" [measured], which is how vcrun2012 -
# the thing the linker needs - fails.
RUN ln -sf /opt/wine-stable/bin/wine /usr/local/bin/wine64

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY with-display.sh /usr/local/bin/with-display
COPY xorg-headless.conf /etc/X11/xorg-headless.conf
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/with-display

WORKDIR /tools
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["bash"]
