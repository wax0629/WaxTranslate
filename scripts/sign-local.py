"""Sign waxtranlate updates with the same private, per-user development identity."""
import fcntl
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

BUNDLE_ID = "local.luma.hovertranslate"
VERSION = "0.29.0"
# Official indygreg/apple-platform-rs release archives.
ARCHIVES = {
    "arm64": ("aarch64", "d1a532150adaf90048260d76359261aa716abafc45c53c5dc18845029184334a"),
    "x86_64": ("x86_64", "14ef11bedd51a8d95eafd767939ae96d5900e5a61511bef75bb21db6e7c74140"),
}


def signer(root, work):
    arch, digest = ARCHIVES[platform.machine()]
    directory = "apple-codesign-{}-{}-apple-darwin".format(VERSION, arch)
    tool = root / directory / "rcodesign"
    if tool.is_file():
        return tool
    url = ("https://github.com/indygreg/apple-platform-rs/releases/download/"
           "apple-codesign%2F{}/{}.tar.gz").format(VERSION, directory)
    archive = work / "tool.tar.gz"
    subprocess.run(["/usr/bin/curl", "--proto", "=https", "-fsSL", "--retry", "2",
                    "--max-time", "90", url, "-o", archive], check=True)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        sys.exit("本地签名工具未通过完整性验证。")
    extracted = work / directory
    extracted.mkdir()
    with tarfile.open(archive) as files:
        for name in ["rcodesign", "COPYING"]:
            with files.extractfile(directory + "/" + name) as src, (extracted / name).open("wb") as dst:
                shutil.copyfileobj(src, dst)
    (extracted / "rcodesign").chmod(0o700)
    extracted.rename(tool.parent)
    return tool


def sign(bundle, current):
    os.umask(0o077)
    root = Path.home() / "Library/Application Support/waxtranlate/BuildSigning"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    root.chmod(0o700)
    with (root / "build.lock").open("a") as lock, tempfile.TemporaryDirectory(dir=root) as tmp:
        fcntl.flock(lock, fcntl.LOCK_EX)
        work = Path(tmp)
        tool = signer(root, work)
        old_is_signed = False
        if current.is_dir():
            info = subprocess.run(["/usr/bin/codesign", "-dv", current], check=True, stderr=subprocess.PIPE)
            old_is_signed = b"Signature=adhoc" not in info.stderr
        identity = root / "identity"
        if not identity.exists():
            if old_is_signed:
                sys.exit("请恢复原有的本机签名密钥后再更新，以保留屏幕录制授权。")
            new = work / "identity"
            new.mkdir()
            subprocess.run(["/usr/bin/openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt",
                            "rsa_keygen_bits:3072", "-out", new / "key.pem"], check=True, stderr=subprocess.DEVNULL)
            subprocess.run(["/usr/bin/openssl", "req", "-x509", "-new", "-sha256", "-days", "3650",
                            "-key", new / "key.pem", "-subj", "/CN=waxtranlate local builds",
                            "-addext", "basicConstraints=critical,CA:FALSE", "-addext", "keyUsage=critical,digitalSignature",
                            "-addext", "extendedKeyUsage=critical,codeSigning", "-out", new / "cert.pem"], check=True)
            new.rename(identity)
        cert = identity / "cert.pem"
        der = subprocess.check_output(["/usr/bin/openssl", "x509", "-in", cert, "-outform", "der"])
        # Apple's requirement language identifies certificate bytes by their SHA-1 fingerprint.
        requirement = 'identifier "{}" and certificate leaf = H"{}"'.format(BUNDLE_ID, hashlib.sha1(der).hexdigest())
        if old_is_signed:
            subprocess.run(["/usr/bin/codesign", "--verify", "--strict", "-R", "=" + requirement, current], check=True)
        req_file = work / "designated.req"
        subprocess.run(["/usr/bin/csreq", "-r", "=" + requirement, "-b", req_file], check=True)
        subprocess.run([tool, "sign", "-C", "/dev/null", "--timestamp-url", "none",
                        "--pem-file", identity / "key.pem", "--pem-file", cert,
                        "--code-requirements-file", req_file, bundle], check=True)
        subprocess.run(["/usr/bin/codesign", "--verify", "--strict", "-R", "=" + requirement, bundle], check=True)


if __name__ == "__main__":
    sign(Path(sys.argv[1]), Path(sys.argv[2]))
