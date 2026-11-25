"""Build an English/Chinese offline, universal macOS DMG. Requires Python 3.12+, CMake and the Swift SDK."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile
from tempfile import TemporaryDirectory
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
# CTranslate2 4.8.5, SentencePiece 0.2.1, and CTranslate2's two enabled submodules.
SOURCES = (
    ("OpenNMT/CTranslate2", "7f59ae114cba0f7d5fb1fe6099142e4c3b0037c8", "b7eb60eee65d5f6a7f1b189db61b80d3e5005d02b8228f59696e6fdada7d9a76"),
    ("google/sentencepiece", "31646a467d2051eb904e0b45de3a73e91fe1c1e3", "b4eb17e6bea5c9380ddd79d04d01d6aa5e280be8f3e3cef1f745a80e6d9451ce"),
    ("google/cpu_features", "8a494eb1e158ec2050e5f699a504fbc9b896a43b", "9b2019dae7608630ab985129a5c3263fc788e4f82e26965a8d8c33b8c035802e"),
    ("gabime/spdlog", "76fb40d95455f249bd70824ecfcae7a8f0930fa3", "4530d53b86d45228a5b8982a8f4fe7d95d3ba8e1944858d3f663732c7e949cb7"),
)
MODELS = (
    ("en-zh", "translate-en_zh-1_9", "433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab"),
    ("zh-en", "translate-zh_en-1_9", "62e7af5a3a48b530e47b7b3e5c78c2de79073ecd815750d2bf3ab35b4a67da2d"),
)
MODEL_FILES = ("README.md", "metadata.json", "sentencepiece.model", "model/model.bin",
               "model/config.json", "model/shared_vocabulary.json")


def run(*args):
    subprocess.run(args, check=True, cwd=ROOT)


def fetch(path, sha, urls):
    def valid(file):
        with file.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest() == sha
    if path.is_file() and valid(path):
        return path
    with TemporaryDirectory(dir=path.parent) as tmp:
        download = Path(tmp) / "download"
        for url in urls:
            try:
                with urllib.request.urlopen(url, timeout=90) as source, download.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
                if not valid(download):
                    raise ValueError(f"SHA-256 mismatch for {path.name}")
                download.replace(path)
                return path
            except (OSError, ValueError) as error:
                print(f"{path.name}: {error}", flush=True)
    raise RuntimeError(f"Could not verify {path.name}")


def sources(cache):
    dirs = []
    for repo, rev, sha in SOURCES:
        archive = fetch(cache / (rev + ".tar.gz"), sha, [f"https://codeload.github.com/{repo}/tar.gz/{rev}"])
        directory = cache / (repo.split("/")[1] + "-" + rev)
        if not directory.exists():
            with TemporaryDirectory(dir=cache) as tmp, tarfile.open(archive) as tar:
                tar.extractall(tmp, filter="data")
                (Path(tmp) / directory.name).rename(directory)
        dirs.append(directory)
    ct2, spm, cpu, spdlog = dirs
    for name, src in (("cpu_features", cpu), ("spdlog", spdlog)):
        shutil.copytree(src, ct2 / "third_party" / name, dirs_exist_ok=True)
    return ct2, spm


def install_models(cache, resources):
    for pair, name, sha in MODELS:
        file = name + ".argosmodel"
        archive = fetch(cache / file, sha, ["https://argos-net.com/v1/" + file,
                                            "https://data.argosopentech.com/argospm/v1/" + file])
        with zipfile.ZipFile(archive) as model:
            for filename in MODEL_FILES:
                dest = resources / "OfflineModels" / pair / filename
                dest.parent.mkdir(parents=True, exist_ok=True)
                with model.open(name + "/" + filename) as source, dest.open("wb") as out:
                    shutil.copyfileobj(source, out)


def install_notices(resources, ct2, spm):
    dest = resources / "ThirdPartyLicenses"
    dest.mkdir()
    for name, src in (("CTranslate2", ct2), ("SentencePiece", spm)):
        for file in [src / "LICENSE", *sorted((src / "third_party").rglob("LICENSE")),
                     *sorted((src / "third_party").rglob("*.license.rst"))]:
            shutil.copyfile(file, dest / (name + "-" + "-".join(file.relative_to(src).parts)))
    # These single-header dependencies carry their notices in the source itself.
    for header in [*(ct2 / "third_party").glob("*.h*"),
                   ct2 / "include/half_float/half.hpp", ct2 / "include/nlohmann/json.hpp"]:
        shutil.copyfile(header, dest / header.name)


def notarize(path, profile):
    run("xcrun", "notarytool", "submit", path, "--keychain-profile", profile, "--wait")


def build(args):
    cache = args.cache.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    ct2, spm = sources(cache)
    binaries, libraries = [], []
    for arch, suffix in (("arm64", "arm64"), ("x86_64", "x64")):
        swift = ROOT / ".build" / ("installer-" + suffix)
        native = (ROOT / ".build" / ("offline-" + arch)).resolve()
        run("cmake", "-S", ROOT / "macos/offline", "-B", native, f"-DCT2_SOURCE={ct2}", f"-DSPM_SOURCE={spm}",
            "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_SYSTEM_NAME=Darwin", "-DCMAKE_SYSTEM_PROCESSOR=" + arch,
            "-DCMAKE_OSX_ARCHITECTURES=" + arch, "-DCMAKE_OSX_DEPLOYMENT_TARGET=15.2")
        run("cmake", "--build", native, "--target", "WaxTranslation", "--parallel", str(args.jobs))
        command = ["swift", "build", "-c", "release", "--triple", arch + "-apple-macosx15.2",
                   "--scratch-path", str(swift), "-j", str(args.jobs)]
        run(*command)
        binpath = subprocess.check_output(command + ["--show-bin-path"], cwd=ROOT, text=True).strip()
        binaries.append(Path(binpath) / "waxtranlate")
        libraries.append(native / "libWaxTranslation.dylib")

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out) as tmp:
        tmp = Path(tmp)
        volume = tmp / "volume"
        volume.mkdir()
        app = volume / "waxtranlate.app"
        run("lipo", "-create", *binaries, "-output", tmp / "waxtranlate")
        run("bash", ROOT / "scripts/stage-macos-app.sh", tmp / "waxtranlate", app)
        frameworks = app / "Contents/Frameworks"
        frameworks.mkdir()
        library = frameworks / "libWaxTranslation.dylib"
        run("lipo", "-create", *libraries, "-output", library)
        resources = app / "Contents/Resources"
        install_models(cache, resources)
        install_notices(resources, ct2, spm)
        for binary in (app / "Contents/MacOS/waxtranlate", library):
            run("lipo", binary, "-verify_arch", "arm64", "x86_64")
        identity = args.identity or "-"
        signing = ["codesign", "--force", "--sign", identity]
        if args.identity:
            signing.extend(["--options", "runtime", "--timestamp"])
        run(*signing, library)
        run(*signing, app)
        run("codesign", "--verify", "--deep", "--strict", app)
        if args.identity:
            archive = tmp / "app.zip"
            run("ditto", "-c", "-k", "--keepParent", app, archive)
            notarize(archive, args.notary_profile)
            run("xcrun", "stapler", "staple", app)
            run("spctl", "--assess", "--type", "execute", app)
        (volume / "Applications").symlink_to("/Applications")
        dmg = tmp / ("WaxTranslate-macOS-Universal" + ("" if args.identity else "-test") + ".dmg")
        run("hdiutil", "create", "-volname", "WaxTranslate", "-srcfolder", volume, "-fs", "HFS+",
            "-format", "UDZO", dmg)
        if args.identity:
            run(*signing, dmg)
            notarize(dmg, args.notary_profile)
            run("xcrun", "stapler", "staple", dmg)
            run("xcrun", "stapler", "validate", dmg)
        run("hdiutil", "verify", dmg)
        dmg.replace(out / dmg.name)
        print(out / dmg.name, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--cache", type=Path, default=Path.home() / "Library/Caches/WaxTranslate-Packaging/dependencies")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--identity", help="Developer ID Application signing identity")
    parser.add_argument("--notary-profile", help="Existing notarytool keychain profile")
    args = parser.parse_args()
    if bool(args.identity) != bool(args.notary_profile):
        parser.error("Supply both signing identity and notary profile for a distribution build.")
    build(args)
