# GitBug-Java

GitBug-Java is a reproducible Java benchmark of recent bugs.

[Visualization](https://nfsaavedra.github.io/gitbug-java)

## Setup GitBug-Java

Requirements:
- Python (Recommended 3.11)
- Poetry (Recommended 1.8 and higher)
- Docker (v20 or higher)
- If you are on Ubuntu/Debian, choose a system with GLIBC 2.32 or 2.34 as some of the dependencies require these versions (A docker image would not be suitable as it would require DinD). 

  For example you can create a virtual machine of ubuntu 21.10 (glibc 2.32). Here is a quick setup of an ubuntu VM:
  - Install multipass (allows to quickly create ubuntu VMs and works on Linux/Mac/Windows). Follow instructions here: https://multipass.run/docs/install-multipass.
  - create an ubuntu image (e.g, 280G in disk space, 16G in memory and 2 cpus): 
    ```bash
    multipass launch 21.10 --disk 280G --memory 16G --cpus 2
    ```
  - login the newly created VM
    ```bash
    multipass shell VM-NAME-PRINTED-LAST-STEP
    ```
  - install docker within the image and add the user to the docker group

Once the above requirements are satisfied within your system or the VM machine is created, clone this repository and execute the following steps:

1. Setup Python environment
    ```bash
    poetry shell
    poetry install --no-root
    ```

    **Note:** Poetry shell will attempt to create a new virtual environment. 
    However, if you are already inside a virtual environment, poetry will use the that environment.
    In such case, the subsequent commands would only work with a Python3.11 environment.

2. Add GitBug-Java and custom Act version to path
    ```bash
    export PATH="$(pwd):$(pwd)/bin:$PATH"
    ```
    **Note:** The above command needs to be executed on every new shell instance
    
3. Run Setup (Installs Docker Image ~50GiB, downloads required dependencies ~80GiB). The downloadable data size is around 130GB. However, after unzipping files, the space taken goes up to 240GB (it goes down after deleting the zipped files).
    ```bash
    gitbug-java setup
    ```

**NOTE: Ensure that all `gitbug-java` commands are executed without using `sudo` to guarantee correct functionality.**

## Use GitBug-Java

1. List all available project ids
```bash
gitbug-java pids
```

2. List all available bug ids
```bash
gitbug-java bids [-p=PID]
```

3. Checkout bug-fix
```bash
gitbug-java checkout BID WORK_DIR [--fixed]
```

4. Run Actions
```bash
gitbug-java run WORK_DIR
```

## Citation

If you use GitBug-Java in your research work, please cite [GitBug-Java: A Reproducible Benchmark of Recent Java Bugs](https://arxiv.org/pdf/2402.02961.pdf)

```bibtex
@inproceedings{gitbugjava,
  title={GitBug-Java: A Reproducible Benchmark of Recent Java Bugs},
  author={Silva, Andr{\'e} and Saavedra, Nuno and Monperrus, Martin},
  booktitle={Proceedings of the 21st International Conference on Mining Software Repositories},
  doi={10.1145/3643991.3644884}
}
```
