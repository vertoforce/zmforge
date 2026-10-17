# bo3-wine plus the X tools zmforge render needs to drive Radiant's 3D camera
# and grab it: xdotool (keys, window lookup), x11-apps (xwd), imagemagick
# (xwd -> png, crop, downscale). Built locally, so not digest-pinned.
FROM bo3-wine:local
RUN set -eux; apt-get update; \
    apt-get install -y --no-install-recommends xdotool x11-apps x11-utils imagemagick; \
    rm -rf /var/lib/apt/lists/*
