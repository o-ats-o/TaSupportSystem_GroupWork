#!/usr/bin/env python3
import os
import subprocess
import sys


def main(argv: list[str]) -> int:
    # 強制的にtorchaudioのsoundfileバックエンドを使う
    env = os.environ.copy()
    env["TORCHAUDIO_USE_SOUNDFILE"] = "1"
    env["TORCHAUDIO_BACKEND"] = "soundfile"

    cmd = ["resemble-enhance", *argv]
    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True, env=env)
        sys.stdout.write(res.stdout)
        sys.stderr.write(res.stderr)
        return 0
    except subprocess.CalledProcessError as e:
        sys.stdout.write(e.stdout or "")
        sys.stderr.write(e.stderr or "")
        return e.returncode
    except FileNotFoundError:
        sys.stderr.write("resemble-enhance not found. Please install it.\n")
        return 127


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
