# Native MicroPython tests

These tests require native `micropython.RingIO`, `micropython.schedule`, `asyncio`, the [micropython-lib unittest package](https://github.com/micropython/micropython-lib/tree/master/python-stdlib/unittest), and `logging` **0.6.2**. CPython/pytest and the old v1.23.0 image do not provide the required native contract.

From the repository root, using Docker and the published Unix image (no custom build):

```sh
image=micropython/unix:v1.29.0@sha256:a176e29293235bc69829edd0e37be68ab77d18fc2b2817cd8cabed3ac564e8fb
mkdir -p .test-deps
docker run --rm --init \
  -v "$PWD/.test-deps:/deps" \
  "$image" -X heapsize=8M -c \
  "import mip; mip.install('unittest', version='0.11.0', mpy=False, target='/deps'); mip.install('logging', version='0.6.2', mpy=False, target='/deps')"

docker run --rm --init --read-only --tmpfs /tmp --entrypoint /bin/sh \
  -v "$PWD:/src:ro" -v "$PWD/.test-deps:/deps:ro" \
  -e MICROPYPATH=/src:/deps:.frozen -w /tmp \
  "$image" -ec '
    micropython -X heapsize=8M /src/test/test_mock_machine.py
    micropython -X heapsize=8M /src/test/test_machine_contract.py
    micropython -X heapsize=8M /src/test/test_example_hardware_revision.py
    micropython -X heapsize=8M /src/test/test_example_tmp117.py
  '
```

The working directory must be writable: existing CSV tests and the qualified-import regression create and remove fixtures there. Put the repository root and installed dependencies on `MICROPYPATH`. Never mount dependencies over `/lib`: that hides the image's Linux dynamic linker. Each native invocation uses an 8 MiB interpreter heap.

All four test files have executable native runner entry points. The four invocations above cover the machine foundation; the separate network suite has its own entry point. No physical devices or board-specific peripheral models are exercised.
