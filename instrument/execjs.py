"""JS sandbox + parse check. node --check is the parser; no dependency needed."""
import hashlib, re, sys, subprocess, tempfile, os
from concurrent.futures import ThreadPoolExecutor

NODE = ["node", "--max-old-space-size=512"]
_cache = {}


def _write(src):
    f = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    f.write(src)
    f.close()
    return f.name


def parses(src):
    p = _write(src)
    try:
        return subprocess.run(NODE + ["--check", p], capture_output=True, timeout=10).returncode == 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.unlink(p)


def run(src, timeout=5.0, lang="js"):
    """-> 'pass' | 'fail:<ErrClass>' | 'timeout' | 'parse_error'. Cached by source hash."""
    if lang == "py":
        return _run_py(src, timeout)
    if lang == "go":
        return _run_go(src, timeout)
    if lang == "ts":
        return _run_ts(src, timeout)
    if lang in SIMPLE:
        return _run_simple(src, timeout, lang)
    if lang == "rs":
        return _run_rs(src, timeout)
    if lang == "java":
        return _run_java(src, timeout)
    key = hashlib.sha1(src.encode()).hexdigest()
    if key in _cache:
        return _cache[key]
    if not parses(src):
        _cache[key] = "parse_error"
        return _cache[key]
    p = _write(src)
    try:
        # ponytail: subprocess isolation only. Kaggle/Docker is the real boundary; add nsjail if this ever runs on a shared host.
        r = subprocess.run(NODE + [p], capture_output=True, timeout=timeout,
                           env={"PATH": os.environ["PATH"], "NODE_OPTIONS": ""})
        if r.returncode == 0:
            out = "pass"
        else:
            # A real keystone fails an assertion. A renamed-identifier splice throws
            # ReferenceError/TypeError -- broken reference, not a wrong decision.
            err = r.stderr.decode("utf8", "replace")
            cls = next((c for c in ("AssertionError", "ReferenceError", "TypeError",
                                    "RangeError", "SyntaxError") if c in err), "Other")
            out = "fail:" + cls
    except subprocess.TimeoutExpired:
        out = "timeout"
    finally:
        os.unlink(p)
    _cache[key] = out
    return out


# Compiled toolchains are CPU-bound per splice; oversubscribing a 4-core box makes healthy
# positions time out and look consequential. Scale workers and patience to the toolchain.
LANG_EXEC = {"js": (8, 5.0), "py": (8, 5.0), "rb": (8, 8.0), "php": (8, 8.0),
             "lua": (8, 8.0), "pl": (8, 8.0), "rs": (2, 90.0), "ts": (4, 25.0), "go": (4, 20.0), "java": (2, 60.0)}


def run_many(srcs, timeout=None, workers=None, lang="js"):
    w, t = LANG_EXEC.get(lang, (8, 5.0))
    workers = workers or w
    timeout = timeout if timeout not in (None, 5.0) else t
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda s: run(s, timeout, lang), srcs))


def _run_py(src, timeout=5.0):
    """Python arm of the instrument. Same contract as the JS path."""
    h = hashlib.sha1(("py" + src).encode()).hexdigest()
    if h in _cache:
        return _cache[h]
    try:
        compile(src, "<gen>", "exec")            # parse check, no subprocess needed
    except SyntaxError:
        _cache[h] = "parse_error"; return "parse_error"
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.py")
        with open(p, "w") as fh:
            fh.write(src)
        try:
            r = subprocess.run([sys.executable, p], capture_output=True, timeout=timeout,
                               env={"PATH": os.environ["PATH"]})
            if r.returncode == 0:
                out = "pass"
            else:
                err = r.stderr.decode("utf8", "replace")
                cls = next((c for c in ("AssertionError", "NameError", "TypeError",
                                        "IndexError", "ValueError", "AttributeError",
                                        "ZeroDivisionError", "SyntaxError") if c in err), "Other")
                out = "fail:" + cls
        except subprocess.TimeoutExpired:
            out = "timeout"
    _cache[h] = out
    return out


# Go is the point of contrast: it separates SYNTAX errors from TYPE errors, which JS and Python
# cannot. `gofmt -e` parses without type-checking; `go run` compiles (types) and executes. That
# gives a three-way split where dynamic languages only have two.
GO_ERRS = [
    ("undefined:", "Undefined"),              # renamed identifier -- artifact, not a decision
    ("declared and not used", "UnusedVar"),   # Go-specific strictness -- artifact
    ("imported and not used", "UnusedImport"),
    ("mismatched types", "TypeError"),
    ("cannot use", "TypeError"),
    ("invalid operation", "TypeError"),
    ("not enough arguments", "TypeError"),
    ("too many arguments", "TypeError"),
    ("index out of range", "IndexError"),
    ("integer divide by zero", "ZeroDivision"),
    ("nil pointer dereference", "NilDeref"),
    ("panic:", "Panic"),
]


def _run_go(src, timeout=20.0):
    """-> 'pass' | 'fail:<Class>' | 'type_error:<Class>' | 'timeout' | 'parse_error'.

    MultiPL-E's Go tasks are Go *test* files (`func TestXxx(t *testing.T)` in a `_test`
    package), so they must run under `go test`, not `go run`. The package clause is rewritten
    to `main` so a single file forms a valid package; that clause lives in the fixed prompt and
    is never spliced, so the rewrite cannot affect the measurement.
    """
    h = hashlib.sha1(("go" + src).encode()).hexdigest()
    if h in _cache:
        return _cache[h]
    env = dict(PATH=os.environ["PATH"], HOME=os.environ.get("HOME", "/tmp"),
               GOCACHE=os.environ.get("GOCACHE", "/tmp/gocache"),
               GOPATH=os.environ.get("GOPATH", "/tmp/gopath"))
    body = re.sub(r"^package\s+\w+", "package main", src, count=1, flags=re.M)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "main_test.go")
        with open(p, "w") as fh:
            fh.write(body)
        with open(os.path.join(d, "go.mod"), "w") as fh:
            fh.write("module m\ngo 1.18\n")
        try:                                    # 1) parse only, no type checking
            r = subprocess.run(["gofmt", "-e", p], capture_output=True, timeout=timeout, env=env)
            if r.returncode != 0:
                _cache[h] = "parse_error"
                return "parse_error"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            _cache[h] = "timeout"
            return "timeout"
        try:                                    # 2) type-check, compile, run the tests
            r = subprocess.run(["go", "test", "-count=1", "./..."], cwd=d,
                               capture_output=True, timeout=timeout, env=env)
            txt = (r.stdout + r.stderr).decode("utf8", "replace")
            if r.returncode == 0:
                out = "pass"
            elif "build failed" in txt or "[build failed]" in txt or "undefined:" in txt \
                    or "cannot use" in txt or "declared and not used" in txt \
                    or "mismatched types" in txt or "imported and not used" in txt:
                cls = next((c for pat, c in GO_ERRS if pat in txt), "Build")
                out = "type_error:" + cls        # parsed cleanly but failed static checks
            else:
                cls = next((c for pat, c in GO_ERRS if pat in txt), "Assertion")
                out = "fail:" + cls
        except subprocess.TimeoutExpired:
            out = "timeout"
    _cache[h] = out
    return out


def _run_ts(src, timeout=25.0):
    """TypeScript: the controlled test of F15 -- JavaScript plus a type checker.

    tsc error codes separate the buckets exactly: TS1xxx are syntax errors, TS2xxx+ are type
    errors. A type error is treated as TERMINAL, matching Go, even though tsc still emits
    runnable JS -- that models a project with a build gate, and it is what makes the
    K_syn / K_type / K_sem split comparable across TS and Go.
    """
    h = hashlib.sha1(("ts" + src).encode()).hexdigest()
    if h in _cache:
        return _cache[h]
    env = dict(PATH=os.environ["PATH"], HOME=os.environ.get("HOME", "/tmp"), NODE_OPTIONS="")
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.ts")
        with open(p, "w") as fh:
            fh.write(src)
        try:
            r = subprocess.run(["tsc", "--noEmit", "--target", "es2020", "--module", "commonjs",
                                "--skipLibCheck", p],
                               capture_output=True, timeout=timeout, env=env)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            _cache[h] = "timeout"
            return "timeout"
        if r.returncode != 0:
            diag = (r.stdout + r.stderr).decode("utf8", "replace")
            codes = re.findall(r"error TS(\d+)", diag)
            if any(c.startswith("1") for c in codes):
                _cache[h] = "parse_error"          # TS1xxx == syntax
                return "parse_error"
            cls = "Undefined" if "Cannot find name" in diag else "TypeError"
            out = "type_error:" + cls              # TS2xxx == type
            _cache[h] = out
            return out
        try:                                        # types clean -> emit and execute
            subprocess.run(["tsc", "--target", "es2020", "--module", "commonjs",
                            "--skipLibCheck", "--outDir", d, p],
                           capture_output=True, timeout=timeout, env=env)
            js = os.path.join(d, "m.js")
            if not os.path.exists(js):
                out = "type_error:NoEmit"
            else:
                rr = subprocess.run(["node", js], capture_output=True, timeout=timeout, env=env)
                if rr.returncode == 0:
                    out = "pass"
                else:
                    err = rr.stderr.decode("utf8", "replace")
                    cls = next((c for c in ("AssertionError", "ReferenceError", "TypeError",
                                            "RangeError") if c in err), "Other")
                    out = "fail:" + cls
        except subprocess.TimeoutExpired:
            out = "timeout"
    _cache[h] = out
    return out


# javac reports syntax and type errors through the same channel, so they are split by message.
JAVA_SYNTAX = ("expected", "illegal start", "reached end of file while parsing",
               "class, interface, enum, or record expected", "not a statement",
               "unclosed string literal", "illegal character")
JAVA_TYPE = ("cannot find symbol", "incompatible types", "bad operand types",
             "cannot be applied", "no suitable method", "might not have been initialized",
             "unreported exception", "is abstract; cannot be instantiated")


def _run_java(src, timeout=40.0):
    """Java: `assert` is a NO-OP unless the JVM is started with -ea. Without it every program
    passes and the run looks perfect while measuring nothing. MultiPL-E's Java tasks also import
    org.javatuples, which is not in the JDK, so JAVATUPLES_JAR must be on the classpath.
    """
    h = hashlib.sha1(("java" + src).encode()).hexdigest()
    if h in _cache:
        return _cache[h]
    jar = os.environ.get("JAVATUPLES_JAR", "")
    cp = ".:" + jar if jar else "."
    env = dict(PATH=os.environ["PATH"], HOME=os.environ.get("HOME", "/tmp"))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "Problem.java")          # class Problem -> file must match
        with open(p, "w") as fh:
            fh.write(src)
        try:
            r = subprocess.run(["javac", "-nowarn", "-cp", cp, "-d", d, p],
                               capture_output=True, timeout=timeout, env=env, cwd=d)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            _cache[h] = "timeout"
            return "timeout"
        if r.returncode != 0:
            diag = (r.stdout + r.stderr).decode("utf8", "replace")
            if any(k in diag for k in JAVA_SYNTAX):
                _cache[h] = "parse_error"
                return "parse_error"
            cls = "Undefined" if "cannot find symbol" in diag else "TypeError"
            out = "type_error:" + cls
            _cache[h] = out
            return out
        try:
            # -ea is load-bearing: without it every assert is a no-op and everything "passes"
            rr = subprocess.run(["java", "-ea", "-cp", cp, "Problem"],
                                capture_output=True, timeout=timeout, env=env, cwd=d)
            if rr.returncode == 0:
                out = "pass"
            else:
                err = rr.stderr.decode("utf8", "replace")
                cls = next((c for c in ("AssertionError", "NullPointerException",
                                        "IndexOutOfBoundsException", "ArithmeticException",
                                        "NumberFormatException", "ClassCastException",
                                        "StackOverflowError") if c in err), "Other")
                out = "fail:" + cls
        except subprocess.TimeoutExpired:
            out = "timeout"
    _cache[h] = out
    return out


# Table-driven interpreted languages: a syntax-check command, a run command, and the error
# names that mean "you broke a reference" rather than "you made a bad decision". Adding a
# language is a table row, not a new function.
SIMPLE = {
    "rb":  {"ext": "rb",  "check": ["ruby", "-c"], "run": ["ruby"],
            "errs": ("NameError", "NoMethodError", "TypeError", "ArgumentError",
                     "ZeroDivisionError", "RuntimeError", "IndexError", "FrozenError")},
    "php": {"ext": "php", "check": ["php", "-l"], "run": ["php"],
            "errs": ("ParseError", "TypeError", "Error", "ArgumentCountError",
                     "DivisionByZeroError", "ValueError")},
    "pl":  {"ext": "pl",  "check": ["perl", "-c"], "run": ["perl"],
            "errs": ("Undefined subroutine", "Can't locate", "Global symbol",
                     "Illegal division by zero", "Not a HASH reference",
                     "Not an ARRAY reference", "Can't call method")},
    "lua": {"ext": "lua", "check": ["luac", "-p"], "run": ["lua"],
            "errs": ("attempt to", "nil value", "bad argument")},
}


def _run_simple(src, timeout=8.0, lang="rb"):
    """-> 'pass' | 'fail:<Class>' | 'timeout' | 'parse_error'. Same contract as every arm."""
    spec = SIMPLE[lang]
    h = hashlib.sha1((lang + src).encode()).hexdigest()
    if h in _cache:
        return _cache[h]
    env = dict(PATH=os.environ["PATH"], HOME=os.environ.get("HOME", "/tmp"))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m." + spec["ext"])
        with open(p, "w") as fh:
            fh.write(src)
        try:
            r = subprocess.run(spec["check"] + [p], capture_output=True, timeout=timeout, env=env)
            if r.returncode != 0:
                _cache[h] = "parse_error"
                return "parse_error"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            _cache[h] = "timeout"
            return "timeout"
        try:
            r = subprocess.run(spec["run"] + [p], capture_output=True, timeout=timeout, env=env)
            if r.returncode == 0:
                out = "pass"
            else:
                err = (r.stdout + r.stderr).decode("utf8", "replace")
                cls = next((c for c in spec["errs"] if c in err), "Assertion")
                out = "fail:" + cls
        except subprocess.TimeoutExpired:
            out = "timeout"
    _cache[h] = out
    return out


def _run_rs(src, timeout=60.0):
    """Rust: a third, unrelated static discipline (affine types, no null, exhaustive matching).

    rustc has no parse-only mode, but its diagnostics separate cleanly: syntax errors are bare
    `error:` messages, type/borrow errors carry an E-code (`error[E0308]`). That gives the same
    three-way split as Go/TypeScript without a separate check pass.
    """
    h = hashlib.sha1(("rs" + src).encode()).hexdigest()
    if h in _cache:
        return _cache[h]
    env = dict(PATH=os.environ["PATH"], HOME=os.environ.get("HOME", "/tmp"))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "m.rs")
        b = os.path.join(d, "m")
        with open(p, "w") as fh:
            fh.write(src)
        try:
            r = subprocess.run(["rustc", "--edition", "2021", "-A", "warnings", "-o", b, p],
                               capture_output=True, timeout=timeout, env=env, cwd=d)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            _cache[h] = "timeout"
            return "timeout"
        if r.returncode != 0:
            err = r.stderr.decode("utf8", "replace")
            # A linker failure is an ENVIRONMENT fault, not a property of the code. It carries
            # no E-code, so without this it would be misclassified as a syntax error and corrupt
            # K_syn. Seen locally on a Mac without a working `cc`.
            if "linking with" in err or "error: linker" in err or "ld: " in err:
                _cache[h] = "timeout"        # treated as unmeasured, never as consequence
                return "timeout"
            codes = re.findall(r"error\[E(\d+)\]", err)
            if codes:
                cls = ("Undefined" if any(c in ("0425", "0433", "0412") for c in codes)
                       else "TypeError")
                out = "type_error:" + cls        # compiled diagnostics with an E-code
            else:
                out = "parse_error"              # bare `error:` == syntax
            _cache[h] = out
            return out
        try:
            rr = subprocess.run([b], capture_output=True, timeout=timeout, env=env, cwd=d)
            if rr.returncode == 0:
                out = "pass"
            else:
                e2 = rr.stderr.decode("utf8", "replace")
                cls = ("Assertion" if "assertion" in e2.lower()
                       else "Overflow" if "overflow" in e2.lower()
                       else "IndexError" if "index out of bounds" in e2 else "Panic")
                out = "fail:" + cls
        except subprocess.TimeoutExpired:
            out = "timeout"
    _cache[h] = out
    return out


def syntax_ok(src, lang="js", timeout=10.0):
    """Syntax check only -- no execution. Used to select parse-preserving counterfactuals (O4)."""
    if lang in SIMPLE:
        spec = SIMPLE[lang]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m." + spec["ext"])
            open(p, "w").write(src)
            try:
                return subprocess.run(spec["check"] + [p], capture_output=True,
                                      timeout=timeout).returncode == 0
            except Exception:
                return False
    if lang == "py":
        try:
            compile(src, "<gen>", "exec"); return True
        except SyntaxError:
            return False
        except Exception:
            return False
    # js / ts / go / java / rs: reuse the full path and read only the parse verdict
    return run(src, timeout, lang) != "parse_error"
