# GitBug-Java

GitBug-Java is a reproducible Java benchmark of recent bugs.

[Visualization](https://nfsaavedra.github.io/gitbug-java)

## Setup GitBug-Java

Requirements:
- Python
- Poetry
- Docker

1. Setup Python environment
```bash
poetry shell
poetry install --no-root
```

2. Add GitBug-Java and custom Act version to path
```bash
export PATH="$(pwd):$(pwd)/bin:$PATH"
```

3. Run Setup (Installs Docker Image ~50GiB, downloads required dependencies ~80GiB)
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
