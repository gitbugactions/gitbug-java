#!/usr/bin/env python

import os, tempfile, shutil
import grp
import docker
from pathlib import Path

# Write a Dockerfile to a temporary directory and build the runner image
base_image = f"catthehacker/ubuntu:full-latest"
runner_image = f"gitbugs-java:base"
tmp_dir = tempfile.mkdtemp()
Path(tmp_dir).mkdir(parents=True, exist_ok=True)
dockerfile_path = Path(tmp_dir, "Dockerfile")
with dockerfile_path.open("w") as f:
    client = docker.from_env()
    dockerfile = f"FROM {base_image}\n"
    # HACK: We set runneradmin to an arbitrarily large uid to avoid conflicts with the host's
    dockerfile += f"RUN sudo usermod -u 4000000 runneradmin\n"
    dockerfile += (
        f"RUN sudo groupadd -o -g {os.getgid()} {grp.getgrgid(os.getgid()).gr_name}\n"
    )
    dockerfile += f"RUN sudo usermod -G {os.getgid()} runner\n"
    dockerfile += f"RUN sudo usermod -o -u {os.getuid()} runner\n"
    f.write(dockerfile)

client.images.build(path=tmp_dir, tag=runner_image, forcerm=True)
shutil.rmtree(tmp_dir, ignore_errors=True)
