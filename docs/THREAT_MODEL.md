# OMNIX threat model notes

## Layer 6 subprocess execution

**What runs.** Layer 6 executes a fixed harness and the target interpreter (for example the same Python that runs OMNIX) to drive property-based checks with synthesized and Fabric-supplied inputs. The code that runs in the child process is the pre-existing function under test and a small, checked-in harness pattern—not strings produced by the LLM that are `eval`’d or unpickled into callables in-process.

**Sandboxing.** The child process is started with a low address-space ceiling (`RLIMIT_AS`, 512MB), a wall-clock `communicate(timeout=...)`, only temporary paths under `/tmp` for the harness, `stdout`/`stderr` pipes, and `start_new_session=True` so a timeout is handled by `killpg` and not by leaving a stray process group attached to the parent.

**Why a subprocess is required.** “Universal” PBT and fuzz-style checks must run the function under test in the language runtime that owns its semantics. Without that, the engine cannot cover multi-language or native-backed targets in a single pipeline.

**Why this beats pickling or eval.** Unpickling or evaluating expressions to obtain callables from LLM-originated or LLM-rewritten data would be arbitrary code execution in the parent. A subprocess with a small entrypoint, argument-only inputs, resource limits, and a timeout only executes code that was already in the project tree plus controlled harness glue.
