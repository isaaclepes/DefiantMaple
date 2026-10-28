# Managed thumbnail budget: internal A1 prerequisite

The selected policy is **5 GiB (5,368,709,120 logical bytes) per library, with no
automatic deletion**. This increment provides internal primitives only. No
production writer imports or calls them; the existing thumbnail cache does not
yet enforce this budget. Whole-list background preparation remains deferred.

## Implementation contract

`defiantmaple.thumbnail_budget` contains a tightening-only policy, observed usage,
and pure additive admission arithmetic. Counts include every ordinary file name,
including unknown, legacy, staging and control files. Hard-link aliases are
charged separately. Existing over-byte-limit usage is reported, never deleted
or treated as free space. File/entry/depth traversal overflow refuses inventory.
The default traversal bounds are 10,000 files, 20,000 entries and depth32;
root ancestry is limited to64 components to bound held descriptors.

The inventory caller must explicitly pin an ordinary private current-user root.
The POSIX adapter opens every ancestor and entry without following symlinks,
compares captured/opened/post-inspection identities, keeps directory handles
through traversal, and refuses observed replacement or mutation. Unsupported
platform capabilities fail closed. There is no Windows inventory adapter in
this increment. Pure accounting and the borrowed stream have no OS-lock or
library-ownership authority.

Inventory is a bounded observation, not an atomic filesystem snapshot. A file
may change after its checks, and unrelated writers can grow the tree. The future
cooperating writer gate is required for admission. This is not a physical-block,
global-account or hostile-writer quota. Entry/depth bounds cannot preempt a
blocking filesystem syscall. A2 must supply supervised execution/lifetime and
cancellation; this synchronous primitive is not a GUI-safe timeout mechanism.

`BoundedOutput` borrows a caller-owned seekable memory buffer or a POSIX binary
file whose non-append descriptor flags can be verified. Append mode and append
descriptors refuse before writing, including append flags hidden by `fdopen`.
Unsupported file-descriptor adapters refuse; no Windows file-backed guarantee is
claimed. Memory buffers remain portable. Flags are rechecked before write/flush;
concurrent external flag mutation after checks remains outside the contract.
The caller supplies a quiescent stream without pending external writes. Writes, seeks and
truncation cannot exceed the chosen ceiling, at most20 MiB. It refuses descriptor
export so an encoder cannot silently bypass `write()` through an exposed fd.
It does not close, unlink, publish, reserve, enroll or recover anything. Existing
bytes above its ceiling refuse construction; partial data after a write failure
remains the caller's responsibility. External writes through aliases or a
malicious underlying stream are outside this cooperative wrapper's contract.

## Acceptance and limitations

Generated tests cover exact arithmetic boundaries and invalid inputs; unknown
and hard-linked usage; over-budget accounting; file/entry/depth overflow; unsafe
root, symlink/FIFO and replacement/mutation refusal; unsupported capability
refusal; exact output boundaries, seek/truncate, partial write errors and actual
Pillow PNG/JPEG encoding through the bounded wrapper. Fixtures verify untouched input bytes, modes and mtimes; injected race changes
are made by the generated test fixture itself. No user media, catalog enrollment, native UI, heavy
benchmark or large-budget allocation is needed.

Local tests are evidence for their recorded source/platform only. They do not
qualify Windows/macOS inventory, a production managed quota, power-loss recovery,
whole-list warming or performance.

## A2 dependencies before an active budget claim

- Establish one canonical, physically verified library/root association across
  GUI and custom CLI destinations. Do not infer authority from UUID/path alone,
  silently adopt legacy roots, or relink copied/moved/restored catalogs.
- Decide and independently review the unique association authority and native
  cross-platform root/kernel-gate adapters. An account-global registry is not
  selected by this prerequisite. No `admission-v1` changes are implied.
- Hold a cancellable root-before-key cooperating-writer gate; no lock expiry or
  PID/age-only takeover. Unknown or incomplete inventory refuses new writes.
- Persist and sync bounded operation-owned capacity before dispatch. Parent loss
  or uncertain child cleanup remains charged and refuses further generation;
  no automatic recovery, pruning or quota deletion.
- Wire the real decoder output to owned pinned staging and the reviewed bound.
  Replace unsafe existing destination deletion/expiry-lock behavior on the
  managed path; preserve existing decoder/original-admission/revision guards.
- Prove no-clobber PNG/manifest publication and exact conservative overlap/entry
  accounting. The earlier provisional24 MiB is insufficient when two20 MiB PNG
  names coexist; final sequencing needs its own reviewed arithmetic.
- Route every current `thumbnail_for` write path, including CLI/package callers,
  through the complete boundary. Keep validated cache reads available above the
  budget and when originals are offline. Budget refusal must not mutate source
  health or asset metadata. No partial gate may be advertised as active5 GiB
  enforcement.
