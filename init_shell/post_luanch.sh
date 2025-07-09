#!/bin/bash

current_path=$(pwd)

ip link set eth0 up
dhclient -r -4 eth0
dhclient -4 eth0

apt update
apt dist-upgrade
add-apt-repository ppa:liujianfeng1994/panfork-mesa
apt update
apt dist-upgrade
apt install -y cmake meson
apt install -y libegl-mesa0 libgbm1 libgl1-mesa-dri libglapi-mesa libglx-mesa0 libmali*
apt install -y pyqt5* python3-pyqt5 qtbase5-dev qtbase5-dev-tools qt5-qmake*
apt install -y libgpiod2

# Build MPP
mkdir -p ~/dev && cd ~/dev
git clone -b jellyfin-mpp --depth=1 https://github.com/nyanmisaka/mpp.git rkmpp
pushd rkmpp
mkdir rkmpp_build
pushd rkmpp_build
cmake \
    -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TEST=OFF \
    ..
make -j $(nproc)
make install

# Build RGA
mkdir -p ~/dev && cd ~/dev
git clone -b jellyfin-rga --depth=1 https://github.com/nyanmisaka/rk-mirrors.git rkrga
meson setup rkrga rkrga_build \
    --prefix=/usr \
    --libdir=lib \
    --buildtype=release \
    --default-library=shared \
    -Dcpp_args=-fpermissive \
    -Dlibdrm=false \
    -Dlibrga_demo=false
meson configure rkrga_build
ninja -C rkrga_build install

# Build the minimal FFmpeg (You can customize the configure and install prefix)
mkdir -p ~/dev && cd ~/dev
git clone --depth=1 https://github.com/nyanmisaka/ffmpeg-rockchip.git ffmpeg
cd ffmpeg
./configure --prefix=/usr --enable-gpl --enable-version3 --enable-libdrm --enable-rkmpp --enable-rkrga
make -j $(nproc)

# Install FFmpeg to the prefix path
make install

apt install -y python3-pip python3-venv

mkdir -p ~/Project && cd ~/Project
python3 -m venv --system-site-packages yolo
source yolo/bin/activate
pip install -U pip
pip install rknn-toolkit-lite2 ultralytics ffmpeg gpiod subprocess numpy threading

cp "$current_path/Project/run.py" .
cp "$current_path/Project/best-rk3588-04_rknn_model" .
cp "$current_path/Project/systemd/py_autostart.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable py_autostart.service
systemctl start py_autostart.service