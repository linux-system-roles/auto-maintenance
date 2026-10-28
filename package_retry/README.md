# Network retry plugin for yum and DNF

`package_retry.py` adds retries to the download layers used by classic yum 3
(Python 2.7) and DNF 4 (Python 3, including DNF-backed `yum`). Coverage includes:

- RPM and delta-RPM downloads, including parallel package downloads.
- Repository metadata, mirrorlists and metalink retrieval.
- Direct-URL RPM downloads and remote signing-key retrieval.
- Other downloads routed through the same urlgrabber/libdnf entry points.

HTTP **400–599**, including **403**, DNS/connect failures, timeouts, and
interrupted connections are eligible. Persistent failures stop after the
configured retry limit. RPM transactions and installation scripts are never
restarted.

## Configuration

The plugin name, installation paths and configuration keys are unchanged.
Replace the previously installed `package_retry.py` to upgrade; keep your
existing configuration.

```ini
[main]
enabled = 1
retries = 3
strategy = fixed
delay = 5
max_delay = 300
```

- `retries`: additional attempts per intercepted download operation, excluding
  the initial attempt. `0` disables additional attempts.
- `strategy`: `fixed` or `exponential`.
- `delay`: nonnegative seconds before the first retry; fixed mode uses it for
  every retry. Fractional seconds are accepted.
- `max_delay`: exponential delay cap, at least `delay`.

For example, `retries = 4`, `strategy = exponential`, `delay = 5` waits 5, 10,
20, and 40 seconds. With `max_delay = 15`, the waits are 5, 10, 15, and 15.
Logs identify plugin retries explicitly:

```text
package_retry: network retry 1/3 in 5 seconds
```

Budgets now apply at the download layer, rather than once per install command
or package batch. A metadata load or a DNF package-target batch can contain
multiple requests. Yum parallel workers retry individual failed transfers.
Native retries and mirror failover remain enabled and can increase the total
HTTP request count. The configured delays are additional to network timeout
and native retry time. Yum parallel retry waits can delay progress reporting
for other in-flight downloads.

## Installation

Run the commands from this directory. Use the instructions for your package
manager; installing on the development host is not necessary.

Classic yum 3 (EL7 default paths):

```sh
sudo install -m 0644 package_retry.py /usr/lib/yum-plugins/package_retry.py
sudo install -m 0644 package_retry.conf /etc/yum/pluginconf.d/package_retry.conf
```

DNF 4 (EL8/EL9): find the plugin directory using the Python interpreter used
by DNF. On EL8, this is normally `/usr/libexec/platform-python`; on EL9,
`python3` normally works:

```sh
python3 -c 'import dnf; print("\n".join(dnf.Base().conf.pluginpath))'
```

Copy the plugin into one of the printed directories, replacing the placeholder:

```sh
sudo install -m 0644 package_retry.py /path/from/command/package_retry.py
sudo install -m 0644 package_retry.conf /etc/dnf/plugins/package_retry.conf
```

Custom yum/DNF `pluginpath` and `pluginconfpath` settings take precedence over
these defaults. Ensure plugins are enabled in the main package manager
configuration. Then run `yum install PACKAGE` or `dnf install PACKAGE` as usual.
Retries log their number and wait time. Disable for one invocation with
`--disableplugin=package_retry`, or set `enabled = 0` in the plugin configuration.

## Scope and compatibility

The plugin patches yum's synchronous urlgrabber retry loop and parallel worker
completion handling. For DNF it patches the Python bindings for libdnf
`Repo.load`, `Repo.downloadMetadata`, `Repo.downloadUrl`,
`Downloader.downloadURL`, and `PackageTarget.downloadPackages`. Hooks are
installed during early plugin configuration and restored when the plugin is
unloaded. Nested metadata/key operations share the outer retry budget.
DNF preserves native package checksum verification and cached-file reuse;
URL downloads to seekable file descriptors are rewound and truncated before
retrying, to prevent partial-response duplication.

This covers the package managers' standard repository/download operations,
not arbitrary network traffic from the process. A third-party plugin using
its own HTTP library, a subprocess or a native entry point outside these hooks
is not intercepted. Downloads made before plugin initialization are also
outside its scope. Direct writes to nonseekable descriptors cannot safely be
replayed and are not retried; DNF's usual URL helpers use seekable temporary
files. DNF 5 has a different API and is not supported.

Dependency, RPM scriptlet, signature, checksum, local disk and TLS certificate
errors are not eligible. Mixed download failures stop when an ineligible
failure is reported. Error classification uses structured urlgrabber codes,
DNF mirror failure callbacks and curl/HTTP message formats. Unrecognized
localized errors without usable codes fail normally.

Transport patches are process-wide while the plugin is loaded. Use one active
plugin instance per process. Other plugins replacing the same methods without
delegating can bypass the retries. These hooks include implementation APIs;
validate against the yum/DNF versions you deploy.

Implementation references:
[urlgrabber](https://github.com/rpm-software-management/urlgrabber/blob/master/urlgrabber/grabber.py),
[libdnf downloader](https://github.com/rpm-software-management/libdnf/blob/dnf-4-master/libdnf/repo/Repo.cpp),
[librepo package downloader](https://github.com/rpm-software-management/librepo/blob/master/librepo/package_downloader.c).

## Testing

From the repository root, run the isolated unit tests:

```sh
python3 -m pytest -v tests/unit/test_package_retry.py
```

Run the live download integration tests with a system Python providing DNF 4,
libdnf and pytest, plus `createrepo_c`. urlgrabber is needed for the yum
transport cases; `dnf-3` or `dnf4` is needed for the CLI case:

```sh
python3 -m pytest -v tests/integration/test_package_retry_dnf.py
```

The integration suite starts an HTTP server in a separate localhost process
and uses temporary repositories and caches. It performs no RPM transactions
and needs no root privileges. Tests cover recovery from 403/404/429/500/503,
metadata and mirrorlist failures, direct URLs, package targets, timeouts,
connection refusal, retry exhaustion, plugin lifecycle, and yum synchronous
and parallel transfers. A real DNF `makecache` subprocess verifies that the
plugin loads early enough to retry metadata 403 responses, and that disabling
the plugin suppresses its retries. Most tests replace sleeps with a callback
that records the delay and restores the server; the CLI test uses actual waits.

Live validation was performed with DNF 4.24 and the installed Python 3
urlgrabber. Full classic yum 3/Python 2.7 integration remains unverified.
