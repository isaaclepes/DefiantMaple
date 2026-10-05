# Opening files in external tools

Focus an asset in the gallery, then choose **Open in Editor** or **Open containing
folder**. The folder action opens the directory; it does not promise to highlight
the file. The action captures the displayed asset identity and revision. Changing
selection, filters or settings while it checks cannot redirect it to another file.

**External tools on this machine…** selects the default application or a trusted
installed executable for each action. Enter an absolute executable path and any
fixed arguments as literal values, one per line. A default application may be a
viewer rather than an editor. The selected file or folder is
added as the last argument. There is no shell command or filename substitution.
Windows `.bat` and `.cmd` wrappers are unsupported. Settings remain local to this
machine, separate from the catalog and outside registered source folders. Moving
or sharing a catalog does not transfer executable trust or change OS associations.
An unavailable local settings location produces a refusal; choose an appropriate
source registration and local configuration before retrying.

Checks run away from the gallery thread. One check or settings operation runs at
a time; **Cancel external check** requests cancellation. Verification has a
five-second deadline, including initial settings loading, startup and catalog
locks. Originals larger than 512 MiB refuse under this operational bound. These
limits do not change supported formats or establish a performance budget.
Missing, denied, nonregular, symlinked or changed files, stale revisions and
unavailable tools refuse visibly. Select/refresh the asset and explicitly retry
only after addressing the stated problem.

Source health describes the last scan. Paused monitoring is ordinary availability;
watching and paused sources may open after current-file checks. Scanning must
finish first. Offline, permission-denied, error or missing entries need an
explicit scan/reconciliation, even if a file has since returned. Opening never
rewrites source health or metadata. Valid individually indexed files also work.

A successful result says a handoff was **requested**. It does not prove an editor
opened, saved or reconciled. The external application belongs to the user and can
continue after the gallery closes. After external edits, run an explicit scan.
If a permitted request loses its acknowledgement, the result is **uncertain**:
check the external application before deciding whether to retry. DefiantMaple
never retries automatically. Closing cancels outstanding checks asynchronously;
if helper cleanup fails, further requests and closing are blocked with visible
feedback instead of claiming clean shutdown.

The final identity check cannot prevent an external change between checking and
the tool's own access. Choose trusted tools and arguments. This milestone uses
mocked default-association tests and a generated read-only native handler; it does
not qualify particular installed editors, Windows/macOS native interactions,
network-share interruption or broader assistive technology. See the
[implementation decision](external-actions-design.md) for the precise bounds.
