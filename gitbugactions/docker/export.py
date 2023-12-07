import os, shutil
import hashlib
import shutil
import uuid
import tempfile
import json
import pickle
import docker
import tarfile
from dataclasses import dataclass
from typing import Dict, List

from docker.models.containers import Container
from docker.models.images import Image


@dataclass
class Layer:
    name: str
    path: str

    def delete(self):
        shutil.rmtree(self.path)


def extract_last_layer(container_id: str, layer_path: str) -> Layer:
    """Extracts the most recent (last) layer of a Docker container.

    A folder correspondent to the layer will be saved on `layer_path`. The
    folder contains a json with information about the layer, a tar file and a
    VERSION file. The function ``add_new_layer`` can be used to import the Layer
    that results from this function to a Docker image.

    Args:
        container_id (str): Id of the Docker container.
        layer_path (str): Path to folder where the layer is saved.

    Returns:
        Layer: Most recent layer in the Docker container.
    """
    layer = None
    tar_path, container_path, manifest_path = "", "", ""

    try:
        client = docker.from_env(timeout=1200)
        container: Container = client.containers.get(container_id)
        container_name = f"test{uuid.uuid4()}"
        # Create image from container
        container.commit("gitbugactions", container_name)

        tar_path = os.path.join(tempfile.gettempdir(), f"{container_name}.tar")
        image: Image = client.images.get(f"gitbugactions:{container_name}")
        # Save image to tar file
        with open(tar_path, "wb") as f:
            for chunk in image.save():
                f.write(chunk)

        container_path = os.path.join(tempfile.gettempdir(), container_name)
        if not os.path.exists(container_path):
            os.mkdir(container_path)

        # Extract only the last layer from the image's tar file
        with tarfile.open(tar_path, "r") as tar:
            tar.extract("manifest.json", container_path)
            manifest_path = os.path.join(container_path, "manifest.json")

            with open(manifest_path, "r") as f:
                layers = json.loads(f.read())[0]["Layers"]
                # Get last layer's name
                layer = os.path.dirname(layers[-1])
                tar.extract(os.path.join(layer, "json"), layer_path)
                tar.extract(os.path.join(layer, "layer.tar"), layer_path)
                tar.extract(os.path.join(layer, "VERSION"), layer_path)
                layer = os.path.dirname(layers[-1])
    finally:
        client.images.remove(image=f"gitbugactions:{container_name}")
        if os.path.exists(tar_path):
            os.remove(tar_path)
        if os.path.exists(manifest_path):
            os.remove(manifest_path)
        if os.path.exists(container_path):
            shutil.rmtree(container_path, ignore_errors=True)

    return Layer(layer, os.path.join(layer_path, layer))


def add_new_layer(image_name: str, layer: Layer, new_image_name: str = None):
    """Creates a Docker image with a new layer added to the original image.

    Args:
        image_name (str): Name of the Docker image on which the layer is added.
        layer (Layer): Layer to be added to the Docker image.
        new_image_name (str, optional): Name to tag the new image. If no
            name is provided the image will not have a tag. The name should
            follow the format 'repository:tag'. Defaults to None.
    """
    client = docker.from_env(timeout=1200)
    image: Image = client.images.get(image_name)
    temp_extract_path, tar_path, final_tar = "", "", ""

    try:
        # Saves the original image to a tar file
        tar_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        with open(tar_path, "wb") as f:
            for chunk in image.save():
                f.write(chunk)

        with tarfile.open(tar_path, "r") as tar:
            temp_extract_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
            tar.extractall(temp_extract_path)

            # Extracts the manifest
            manifest_path = os.path.join(temp_extract_path, "manifest.json")
            with open(manifest_path, "r") as f:
                manifest = json.loads(f.read())

            # Adds the new layer to the manifest
            manifest[0]["Layers"].append(os.path.join(layer.name, "layer.tar"))

            # Rewrites manifest
            with open(manifest_path, "w") as f:
                f.write(json.dumps(manifest))

            # Adds the layer content's hash to the json that defines the image
            json_path = os.path.join(temp_extract_path, manifest[0]["Config"])
            with open(json_path, "r") as f:
                json_file = json.loads(f.read())
            layer_digest = hashlib.sha256()
            with open(os.path.join(layer.path, "layer.tar"), "rb") as f:
                layer_digest.update(f.read())
            json_file["rootfs"]["diff_ids"].append(f"sha256:{layer_digest.hexdigest()}")

            # Rewrites the json
            with open(json_path, "w") as f:
                f.write(json.dumps(json_file))

            # Copies the layer to inside the folder
            shutil.copytree(
                layer.path, os.path.join(temp_extract_path, layer.name), symlinks=True
            )

            # Creates a tar file with the modified version of the original image
            final_tar = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
            with tarfile.open(final_tar, "w") as f_tar:
                for file in os.listdir(temp_extract_path):
                    f_tar.add(os.path.join(temp_extract_path, file), arcname=file)

            # Loads new image and tags it
            with open(final_tar, "rb") as f:
                image: Image = client.images.load(f.read())[0]
                if new_image_name != None:
                    repository, tag = new_image_name.split(":")
                    image.tag(repository, tag)
    finally:
        if os.path.exists(temp_extract_path):
            shutil.rmtree(temp_extract_path)
        if os.path.exists(tar_path):
            os.remove(tar_path)
        if os.path.exists(final_tar):
            os.remove(final_tar)


@dataclass
class DiffNode:
    children: Dict[str, "DiffNode"]
    kind: int
    path: str
    full_path: str

    @property
    def is_file(self) -> bool:
        return len(self.children) == 0


def extract_diff(container_id: str, diff_file_path: str, ignore_paths: List[str] = []):
    """Extracts all the files in the diff of a Docker container.

    The resulting file will be a compressed tar file (tar.gz) which contains
    all the files changed in the Docker container. The files will be structured
    as they were on the Docker container (i.e, if the file `/test/test.txt` was
    changed, the file `test.txt` will be on the folder `test`). The tar file
    also contains a pickle file called `diff.pkl`. The pickle is created from
    the root ``DiffNode`` which contains the tree that represents the diff of
    the Docker container. We can apply the extracted diff to another Docker
    container using ``apply_diff``.

    Args:
        container_id (str): Id of the Docker container.
        diff_file_path (str): Path on which the diff file will be saved.
        ignore_paths (List[str], optional): Paths that will not be extracted.
            For instance, if the '/tmp' folder is on the list, any files
            changed on this folder or its child folders will not be on the
            diff file. Defaults to [].
    """
    save_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
    client = docker.from_env(timeout=600)
    container: Container = client.containers.get(container_id)

    diff = container.diff()
    parent_node = DiffNode({}, -1, "/", "/")

    # Create diff tree
    for change in diff:
        if any(map(lambda path: change["Path"].startswith(path), ignore_paths)):
            continue

        # The index removes the empty string from the beggining (/path...)
        path = change["Path"].split(os.sep)[1:]
        current_node = parent_node

        for p in path:
            if p not in current_node.children:
                current_node.children[p] = DiffNode({}, -1, p, "")
            current_node = current_node.children[p]

        # Types of kinds (what happened to the file):
        # 0 -> Changed, 1 -> Created, 2 -> Deleted
        current_node.kind = change["Kind"]
        current_node.full_path = change["Path"]

    if not os.path.exists(save_path):
        os.makedirs(save_path)

    def handle_node(node: DiffNode):
        """
        Goes through the diff tree and gets each changed/created file from the container
        """
        for _, child in node.children.items():
            if child.kind == 2:
                continue
            # if a directory was created we can download all the content there
            elif child.is_file or child.kind == 1:
                path = os.path.join(save_path, child.full_path[1:])
                with open(f"{path}.tar", "wb") as f:
                    bits, _ = container.get_archive(child.full_path)
                    for chunk in bits:
                        f.write(chunk)

                with tarfile.open(f"{path}.tar", "r") as f:
                    f.extractall(os.path.dirname(path))

                os.remove(f"{path}.tar")
                continue
            # If a folder was changed, it means a file was change inside it
            # so we create the folder
            else:
                os.makedirs(os.path.join(save_path, child.full_path[1:]))
            handle_node(child)

    handle_node(parent_node)

    with open(os.path.join(save_path, "diff.pkl"), "wb") as f:
        pickle.dump(parent_node, f)
    # Save diff files and pickle in a compressed tar file
    with tarfile.open(diff_file_path, "w:gz") as tar_gz:
        tar_gz.add(save_path, arcname="diff")

    shutil.rmtree(save_path, ignore_errors=True)


def apply_diff(container_id: str, diff_file_path: str):
    """Applies the diff from a diff file to a Docker container.

    The diff file is created by the function ``extract_diff``. Even though the
    function works for any Docker container, the Docker container should have the
    same files as the Docker container used to create the diff file before the
    changes from the diff file were made. The expected workflow is the following:

    Create container B from image A -> extract_diff(B) -> diff_file
    Create container C from image A -> apply_diff(C, diff_file) -> clone of B (C)

    Args:
        container_id (str): Id of the Docker container.
        diff_file_path (str): Path to diff file created by ``extract_diff``
    """
    client = docker.from_env(timeout=600)
    container: Container = client.containers.get(container_id)
    diff_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))

    with tarfile.open(diff_file_path, "r:gz") as tar_gz:
        tar_gz.extractall(diff_path)

    with open(os.path.join(diff_path, "diff", "diff.pkl"), "rb") as f:
        parent_node: DiffNode = pickle.load(f)

    def handle_removes(node: DiffNode):
        for _, child in node.children.items():
            handle_removes(child)

        if not node.is_file and node.kind == 2:
            container.exec_run(f"rmdir {node.full_path}")
        elif node.is_file and node.kind == 2:
            container.exec_run(f"rm {node.full_path}")

    # Copy all changed and created files to the container
    for file in os.listdir(os.path.join(diff_path, "diff")):
        if file != "diff.pkl":
            random_path = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
            # The files should be in tar format
            with tarfile.open(random_path, "w") as tar:
                tar.add(os.path.join(diff_path, "diff", file), arcname=file)
            with open(random_path, "rb") as tar:
                container.put_archive("/", tar.read())
            os.remove(random_path)

    # Removes the files that were removed in the diff
    handle_removes(parent_node)
    shutil.rmtree(diff_path, ignore_errors=True)


def create_diff_image(base_image: str, new_image_name: str, diff_file_path: str):
    """Creates a new image with the diff file applied to the base image

    The diff file is created by the function ``extract_diff``. Even though the
    function works for any Docker image, the Docker image should have the
    same files as the Docker container used to create the diff file before the
    changes from the diff file were made. The expected workflow is the following:

    Create container B from image A -> extract_diff(B) -> diff_file
    create_diff_image(A, C, diff_file) -> Create container D from image C -> clone of B (D)

    Args:
        base_image_name (str): Name of the base image. The name
            should follow the format 'repository:tag'.
        new_image_name (str): Name to tag the new image. The name
            should follow the format 'repository:tag'.
        diff_file_path (str): Path to diff file created by ``extract_diff``
    """
    client = docker.from_env(timeout=300)
    container: Container = client.containers.run(base_image, detach=True)
    apply_diff(container.id, diff_file_path)
    repository, tag = new_image_name.split(":")
    container.commit(repository=repository, tag=tag)
    container.stop()
    container.remove(v=True, force=True)
