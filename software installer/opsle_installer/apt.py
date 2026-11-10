import shutil
import subprocess


def apt_available() -> bool:
    return shutil.which("apt-get") is not None


def installed_packages() -> set[str]:
    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Package}\t${db:Status-Status}\n"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {
        fields[0]
        for line in result.stdout.splitlines()
        if len(fields := line.split("\t")) == 2 and fields[1] == "installed"
    }


def update_command() -> list[str]:
    return ["apt-get", "-y", "upgrade"]


def package_install_command(packages: list[str], upgrade_only: bool = False) -> list[str]:
    command = ["apt-get", "install", "-y"]
    if upgrade_only:
        command.append("--only-upgrade")
    return [*command, "--", *packages]
