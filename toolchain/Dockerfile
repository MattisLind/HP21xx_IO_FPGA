# Runtime dependencies only. Mount a locally supplied ISE 14.7 Linux
# installation read-only; no vendor software or license is included.
FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates make python3 \
    libc6 libstdc++6 libgcc-s1 zlib1g libncurses5 libtinfo5 \
    libx11-6 libxext6 libxrender1 libxtst6 libxi6 libsm6 libice6 \
    libglib2.0-0 libfreetype6 libfontconfig1 libusb-0.1-4 libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
CMD ["bash"]
