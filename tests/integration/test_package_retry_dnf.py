# SPDX-License-Identifier: MIT
"""Real DNF 4/libdnf downloads against a fault-injecting localhost server.

Run with a system Python providing dnf, libdnf, pytest and createrepo_c.
No root privileges, repository configuration changes or RPM transactions.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import types

import pytest

dnf = pytest.importorskip("dnf")
libdnf = pytest.importorskip("libdnf")
import dnf.repo  # noqa: E402
import dnf.util  # noqa: E402
import libdnf.error  # noqa: E402
import libdnf.repo  # noqa: E402


@pytest.fixture
def network(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    payload = b"test download contents\n"
    (root / "test.rpm").write_bytes(payload)
    # Generate a valid empty repository, without needing a real RPM.
    metadata_root = tmp_path / "metadata"
    metadata_root.mkdir()
    subprocess.run(
        ["createrepo_c", str(metadata_root)], check=True, capture_output=True
    )
    (metadata_root / "repodata").rename(root / "repodata")
    state = types.SimpleNamespace(
        status=503, blocked=True, requests=[], waits=[], failure_path=None
    )

    control = tmp_path / "control.json"

    def update():
        temporary = control.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "status": state.status,
                    "blocked": state.blocked,
                    "failure_path": state.failure_path,
                }
            )
        )
        temporary.replace(control)

    state.update = update
    update()
    process = subprocess.Popen(
        [
            sys.executable,
            str(Path(__file__).with_name("retry_http_server.py")),
            str(root),
            str(control),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    state.url = "http://127.0.0.1:" + process.stdout.readline().strip()
    source = Path(__file__).resolve().parents[2] / "package_retry/package_retry.py"
    spec = importlib.util.spec_from_file_location("network_retry_live", source)
    plugin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plugin)

    def sleep(seconds):
        state.waits.append(seconds)
        state.blocked = False
        update()

    monkeypatch.setattr(plugin, "time", types.SimpleNamespace(sleep=sleep))
    hooks = plugin.Hooks(plugin.Policy(retries=2, delay=0.01), lambda msg: None)
    hooks.install_dnf(libdnf.repo, dnf.repo, (RuntimeError, libdnf.error.Error))
    base = dnf.Base()
    base.conf.cachedir = str(tmp_path / "cache")
    base.conf.persistdir = str(tmp_path / "persist")
    base.conf.logdir = str(tmp_path / "logs")
    base.conf.retries = 1
    base.conf.timeout = 1
    base.conf.proxy = ""
    state.base, state.hooks, state.plugin, state.payload = base, hooks, plugin, payload
    try:
        yield state
    finally:
        hooks.close()
        base.close()
        process.terminate()
        process.wait(timeout=5)
        process.stdout.close()


@pytest.mark.parametrize("status", [403, 404, 429, 500, 503])
def test_direct_url(network, status):
    network.status = status
    network.update()
    with dnf.util._urlopen(network.url + "/test.rpm", network.base.conf) as stream:
        assert stream.read() == network.payload
    assert network.waits == [0.01]


def make_repo(network):
    repo = dnf.repo.Repo("retry-test", network.base.conf)
    repo.baseurl = [network.url]
    repo.repo_gpgcheck = False
    repo.gpgcheck = False
    repo.skip_if_unavailable = False
    repo.retries = 1
    return repo


def test_repo_url(network):
    repo = make_repo(network)
    with dnf.util._urlopen(network.url + "/test.rpm", repo=repo) as stream:
        assert stream.read() == network.payload
    assert network.waits == [0.01]


@pytest.mark.parametrize("mirrorlist", [False, True])
def test_metadata_load(network, mirrorlist):
    repo = make_repo(network)
    if mirrorlist:
        repo.baseurl = []
        repo.mirrorlist = network.url + "/mirrorlist"
        network.failure_path = "/mirrorlist"
    else:
        network.failure_path = "/repodata/repomd.xml"
    network.update()
    assert repo.load()
    assert network.waits == [0.01]
    assert repo.metadata is not None


def test_metadata_download(network, tmp_path):
    repo = make_repo(network)
    destination = tmp_path / "download"
    destination.mkdir()
    repo._repo.downloadMetadata(str(destination))
    assert (destination / "repodata/repomd.xml").exists()
    assert network.waits == [0.01]


def test_package_target(network, tmp_path):
    target = libdnf.repo.PackageTarget(
        network.base.conf._config,
        network.url + "/test.rpm",
        str(tmp_path / "out.rpm"),
        libdnf.repo.PackageTarget.ChecksumType_SHA256,
        hashlib.sha256(network.payload).hexdigest(),
        len(network.payload),
        None,
        True,
        0,
        0,
        None,
    )
    targets = libdnf.repo.VectorPPackageTarget([target])
    libdnf.repo.PackageTarget.downloadPackages(targets, True)
    assert (tmp_path / "out.rpm").read_bytes() == network.payload
    assert target.getErr() is None
    assert network.waits == [0.01]


def test_exhaustion(network, monkeypatch):
    monkeypatch.setattr(network.plugin.time, "sleep", network.waits.append)
    with pytest.raises(IOError):
        dnf.util._urlopen(network.url + "/test.rpm", network.base.conf)
    assert network.waits == [0.01, 0.01]


def test_plugin_lifecycle(network, tmp_path):
    network.hooks.close()
    (tmp_path / "package_retry.conf").write_text("[main]\nretries=1\ndelay=0.02\n")
    network.base.conf.pluginconfpath = [str(tmp_path)]
    plugin = network.plugin.PackageRetry(network.base, None)
    original = libdnf.repo.Repo.load
    plugin.pre_config()
    wrapped = libdnf.repo.Repo.load
    plugin.config()
    assert libdnf.repo.Repo.load is wrapped
    try:
        assert make_repo(network).load()
        assert network.waits == [0.02]
    finally:
        plugin.unload()
    assert libdnf.repo.Repo.load is original


def test_timeout(network):
    network.status = "timeout"
    network.update()
    with dnf.util._urlopen(network.url + "/test.rpm", network.base.conf) as stream:
        assert stream.read() == network.payload
    assert network.waits == [0.01]


def test_connection_refused(network, monkeypatch):
    import socket

    monkeypatch.setattr(network.plugin.time, "sleep", network.waits.append)
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))  # Reserve a port without listening on it.
        url = "http://127.0.0.1:%d/test.rpm" % unused.getsockname()[1]
        with pytest.raises(IOError):
            dnf.util._urlopen(url, network.base.conf)
    assert network.waits == [0.01, 0.01]


@pytest.mark.parametrize("operation", ["urlread", "urlopen", "urlgrab", "async"])
def test_urlgrabber(network, tmp_path, operation):
    grabber = pytest.importorskip("urlgrabber.grabber")
    hooks = network.plugin.Hooks(
        network.plugin.Policy(retries=2, delay=0.01), lambda msg: None
    )
    hooks.install_yum(grabber)
    try:
        url = network.url + "/test.rpm"
        if operation == "urlread":
            assert grabber.urlread(url, retry=1) == network.payload
        elif operation == "urlopen":
            stream = grabber.urlopen(url, retry=1)
            try:
                assert stream.read() == network.payload
            finally:
                stream.close()
        else:
            destination = tmp_path / "yum-download"
            options = {"retry": 1}
            if operation == "async":
                options["async_"] = (network.url, 1)
            grabber.urlgrab(url, str(destination), **options)
            if operation == "async":
                grabber.parallel_wait()
            assert destination.read_bytes() == network.payload
        assert network.waits == [0.01]
    finally:
        hooks.close()


def test_cli_makecache_403(network, tmp_path):
    import shutil

    executable = shutil.which("dnf-3") or shutil.which("dnf4")
    if not executable:
        pytest.skip("DNF 4 CLI not installed")
    network.status = 403
    network.update()
    plugin_directory = Path(__file__).resolve().parents[2] / "package_retry"
    (tmp_path / "package_retry.conf").write_text(
        "[main]\nenabled=1\nretries=2\ndelay=0.01\n"
    )
    config = tmp_path / "dnf.conf"
    config.write_text(
        "[main]\nplugins=1\npluginpath=%s\npluginconfpath=%s\nreposdir=%s\n"
        "cachedir=%s\npersistdir=%s\nlogdir=%s\nproxy=\n"
        "[retry-test]\nname=Retry test\nbaseurl=%s\n"
        "enabled=1\nretries=1\ntimeout=1\nskip_if_unavailable=0\n"
        "gpgcheck=0\nrepo_gpgcheck=0\n"
        % (
            plugin_directory,
            tmp_path,
            tmp_path / "no-repos",
            tmp_path / "cli-cache",
            tmp_path / "cli-persist",
            tmp_path / "cli-logs",
            network.url,
        )
    )
    command = [
        executable,
        "-c",
        str(config),
        "--releasever=1",
        "--setopt=varsdir=" + str(tmp_path / "no-vars"),
        "makecache",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    assert result.returncode != 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "package_retry: network retry 1/2 in 0.01 seconds" in output
    assert "package_retry: network retry 2/2 in 0.01 seconds" in output
    assert output.count("package_retry: network retry") == 2
    result = subprocess.run(
        command + ["--disableplugin=package_retry"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0, result.stdout + result.stderr
    assert "package_retry: network retry" not in result.stdout + result.stderr
