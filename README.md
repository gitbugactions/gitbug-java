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
poetry install
```

2. Add GitBug-Java and custom Act version to path
```bash
export PATH="$(pwd):$(pwd)/bin:$PATH"
```

3. Run Setup (Installs Docker Image ~50GiB, downloads required dependencies ~80GiB)
```bash
gitbug-java setup
```

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
gitbug-java checkout PID BID WORK_DIR [--fixed]
```

4. Run Actions
```bash
gitbug-java run WORK_DIR
```

## Contents of GitBug-Java

Please refer to the paper
