## 2024-10-15 - [Pathlib vs OS Path]
**Learning:** `Path(path).is_file()` is significantly slower than `os.path.isfile(path)` because of the object instantiation overhead. For functions called frequently with string inputs during path scanning, checking `isinstance(path, Path)` and falling back to `os.path.isfile(path)` yields a ~4x speedup.
**Action:** Always prefer `os.path` functions for hot path file checks unless object-oriented path manipulation is required.

## 2024-10-15 - Unnecessary Spin Loop in stream reading
**Learning:** `subprocess.Popen.stdout.readline()` on a blocking pipe automatically blocks until a full line is received or EOF is reached. A spin loop checking `proc.poll()` with `time.sleep()` when `readline()` returns empty actually artificially delays EOF detection, because an empty string already exclusively indicates EOF on a blocking stream.
**Action:** Remove `time.sleep` and `proc.poll()` checks after `readline()`; just break when `readline()` returns an empty string.

