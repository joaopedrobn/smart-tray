# Licensing and binary redistribution

Project-authored Python/QML code is MIT. Icons and canvas illustrations are drawn
in code; personal photos/videos are excluded. Screenshots show actual QML rendered
with synthetic states. Brand names describe integrations, not endorsement.

The offline RGBIC codec and examples derive from Tuya Ray Materials, MIT, with its
original notice retained. TinyTuya is MIT; cryptography has Apache-2.0/BSD terms.
Reference dependency versions and available license texts are under `licenses/`.
Python's license applies to the bundled interpreter; PyInstaller has a bootloader
exception. This does not relicense third-party components as MIT.

## Qt and PySide6

Consult [Qt licensing](https://doc.qt.io/qt-6/licensing.html) and
[LGPL obligations](https://www.qt.io/development/open-source-lgpl-obligations).
License choices vary by module; some open-source addons are GPL-only. The app uses
Core/Gui/Widgets/Network/Qml/Quick/QuickControls2 and Canvas, not Quick 3D models.

PyInstaller's QML hook can collect unused modules. **The previous private build
contained unused Quick 3D libraries. Do not upload that build or its ZIP.** Before
any binary release, inventory exact DLLs and QML plugins, remove unused GPL-only
components or comply with their terms, and verify the resulting app.

For an LGPL dynamic distribution, retain notices/license texts, provide corresponding
library source under its license and permit compatible library replacement/relinking.
Do not impose conflicting reverse-engineering restrictions. Record exact dependency
versions and corresponding source; modifications need their source changes too.

Onedir keeps libraries separate. Users may replace compatible libraries under
`_internal/PySide6` or rebuild with locally built PySide6/Qt using the published
application source. Use a coherent compatible toolchain rather than mixing ABI versions.

## Release gate

Source publication and binary publication are separate. This preparation uploads
neither automatically. A release asset must contain no configured devices or private
build data and must pass module-by-module dependency review. The Windows build is
unsigned. Owner approval is required after the security and redistribution gates.
