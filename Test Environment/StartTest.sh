#!/bin/sh

# 保存当前目录
pwdn=$(pwd)
mode="$1"
build_dir="${pwdn}/builds"

if [ "${mode}" = "server" ] || [ "${mode}" = "client" ]; then
	build_dir="${build_dir}/${mode}"
fi

mkdir -p "${build_dir}"
rm -f "${build_dir}/ConnectCore-*.pyz"

# 打包 ConnectCore
cd .. || exit 1
python3 -m mcdreforged pack -o "${build_dir}"

# 回到最初目录并启动
cd "${build_dir}" || exit 1
python3 ./ConnectCore-*.pyz "$@"
