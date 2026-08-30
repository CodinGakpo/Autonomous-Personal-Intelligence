import subprocess


def test_architecture_contracts_pass():
    result = subprocess.run(
        ["lint-imports"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
