## Fixing tox + pip-tools Dependency Split (Windows / Linux)

The dependency architecture idea is correct, but the compilation flow needs adjustment.

The issue was that both generated files were compiled from the same `requirements.in`, causing `pip-compile` to resolve Linux-only transitive dependencies into the shared lock file.

As a result, `requirements-base.txt` ended up containing packages such as:

```text
nvidia-cufile
cuda-toolkit
nvidia-cufft
```

even though they were not explicitly declared.

This happened because:

```text
torch
 └── GPU dependency resolution
      └── CUDA packages
```

---

## Recommended Structure

### requirements.in (Cross-platform dependencies only)

```txt
nltk>=3.9.1
textblob>=0.18.0
numpy>=1.26.0
pandas>=2.2.0
scikit-learn>=1.4.0
matplotlib>=3.10.9
streamlit>=1.33.0

openai>=1.30.0
ollama>=0.3.0

faiss-cpu>=1.7.4

torch>=2.1.0
torchvision>=0.16.0

sentence-transformers>=3.0.0

pytest>=9.0.3
faker>=40.15.0
pylint>=4.0.5

py2neo>=2021.2.4
pyvis>=0.3.2

pytest-html>=4.2.0
```

---

### requirements-linux.in

```txt
-r requirements.in

triton==3.7.0
nvidia-nccl-cu13==2.29.7
nvidia-nvshmem-cu13==3.4.5
```

---

### requirements-windows.in

```txt
-r requirements.in
```

(Optional placeholder for future Windows-specific constraints.)

---

## Compile Dependency Files

### Generate Base Cross-Platform Lock

```bash
pip-compile requirements.in \
  -o requirements-base.txt
```

### Generate Linux GPU Stack

```bash
pip-compile requirements-linux.in \
  -o requirements-linux.txt
```

Do **not** compile Linux dependencies directly from `requirements.in`.

---

## Configure tox

### tox.ini

```ini
[tox]
envlist = py312

[testenv]
deps =
    -r requirements-base.txt

commands =
    pytest tests -v
```

Avoid custom `install_command` unless necessary.

---

## Clean Existing Environment

```bash
rmdir /s .tox
del requirements-base.txt
del requirements-linux.txt
```

---

## Rebuild

```bash
pip-compile requirements.in -o requirements-base.txt
pip-compile requirements-linux.in -o requirements-linux.txt

tox -r -e py312
```

---

## Verify No Linux GPU Packages Leaked Into Base

```bash
findstr /i "nvidia cuda triton" requirements-base.txt
```

Expected output:

```text
(no output)
```

If `requirements-base.txt` still contains `nvidia-*`, then GPU dependencies are entering transitively (commonly through `torch`) and should be isolated further.
