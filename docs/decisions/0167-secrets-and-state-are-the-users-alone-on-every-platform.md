# 0167. CLANK_HOME's secrets and state are the user's alone on every platform: on Windows, an access list of their own

- Status: Accepted (the audit of 2026-10-30); revises design 0001 §7.2 and design 0028 §4
- Date: 2026-11-05
- Decided by: the audit's plan for 0.3.0b8, which asked for the user and SYSTEM alone, inheritance off, done through
  the Windows API or icacls, and checked by `clank doctor`

## Context

- `CLANK_HOME/secrets/` holds the keys and tokens the owner gives Clank (a cloud provider's API key, Notion's secret,
  an MCP server's keys), and `CLANK_HOME/state/` holds the local token that opens Clank's API and the state database.
  Design 0001 §7.2 and design 0002 §2.8 say they are readable only by the user.
- `Home.ensure` made each one mode 0700. That holds them to their user on Linux and macOS, but Windows ignores a
  file's mode: a folder takes the access list of the folder above it. Under the user's profile that is usually the
  user, SYSTEM and Administrators, but a profile's list is whatever was granted on it (an account a tool's sandbox
  runs as, for one), and a CLANK_HOME outside the profile (`D:\clank`) takes the drive's, which lets every signed-in
  user read.
- `clank doctor` did not look at who may open them.

## Decision

- **On Windows, `Home.ensure` gives secrets/ and state/ an access list of their own** (`clank/kernel/private.py`):
  protected from the folder above (inheritance off), with two entries alone, full control for the user Clank runs as
  (its process's token's SID) and for SYSTEM, each inherited by every file and folder made inside (object and
  container inherit). What is already inside then takes the same two entries in place of what it inherited. On Linux
  and macOS each stays mode 0700.
- **The list is read first and written only when it differs**, so a start costs one read of each folder's list, and a
  list put right is never written again. A list changed since (an entry added by hand) is put right at the next start.
- **It goes through Windows' own security calls** (`GetNamedSecurityInfoW`, `SetNamedSecurityInfoW` and the SID calls
  of advapi32, through ctypes, as `infolder` reaches kernel32): no program is started at every start, and nothing
  localized is read.
- **A folder Clank cannot make private stops it**, as a failed `chmod` does elsewhere: the error names the folder and
  Windows' reason.
- **`clank doctor` says who else may open them, and changes nothing**: "Only you can open secrets and state" passes when
  only the user and SYSTEM may (the user alone elsewhere), and otherwise warns, naming each other entry (the account's
  name, its SID when Windows knows none; what it allows or denies; whether it comes from the folder above) with the
  commands that remove it, for the owner to run: `icacls "<folder>" /remove "*<SID>"` for an entry of the folder's own,
  and `icacls "<folder>" /inheritance:r /grant:r "*<user>:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F"` when entries come from the
  folder above (`chmod 700 <folder>` elsewhere). It says too that Clank's service puts them right as it starts.
  `clank setup`'s checklist shows the same words as an item of its own, only while someone else may open them,
  offered and not required, its commands never run by Clank.

## Alternatives considered

- **Run icacls at every start**: a program started each time, and its output is in the system's language, so reading
  the list back means reading localized names; the doctor names icacls only as the command the owner runs.
- **pywin32**: a new dependency for a handful of calls that ctypes reaches already, as `infolder` does.
- **Python's own `mkdir(mode=0o700)`**, which since 3.13 (and in the 3.12 releases with its fix) gives a new folder a
  protected list: it applies only when the folder is made, never to a folder already there (every existing
  CLANK_HOME), its list keeps Administrators, and it depends on the Python release.
- **Keep Administrators in the list**, as the profile's own list does: an administrator can still take a folder's
  ownership, but leaving the group out means a program run by another administrator account cannot read the keys
  without doing that first. The owner's own account is in the list by its SID whether or not it is an administrator.
- **Encrypt the secrets** (Windows' DPAPI): it would keep the keys from other accounts, but not the local token, which
  every client (the console, the commands, VS Code's extension) reads as a file, nor the state database; an access
  list covers both folders alike.
- **Only report, never change the list**: a CLANK_HOME made before this, or outside the profile, would stay open until
  the owner acted; Clank already sets the mode elsewhere at every start.

## Consequences

- secrets/ and state/ are the user's alone on Windows wherever CLANK_HOME is, from the first start of this version on.
  An account another tool runs as, granted access to the profile or to CLANK_HOME, no longer reads them, the local
  token among them, so such a tool no longer reaches Clank's API on its own.
- A CLANK_HOME on a drive that keeps no access lists (FAT, exFAT) or a share that refuses them stops Clank at its start,
  saying why, as a failed `chmod` does on Linux.
- The other folders of CLANK_HOME (config/, logs/, library/, artifacts/) keep what they inherit, as before.
- The doctor has one more check, and its answer is the same on Windows and elsewhere: who else may open the folders,
  and how to take it away.
