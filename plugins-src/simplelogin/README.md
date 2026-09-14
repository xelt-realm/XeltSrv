# SimpleLogin

Local login plugin for Paper servers (used by XeltSrv). No external accounts, no database server:
passwords are stored as salted SHA-256 hashes in `plugins/SimpleLogin/users.yml`.

## Behavior

- **Minecraft 1.21.6+ clients** (detected via ViaVersion): after joining, a dialog asks for
  registration (password + confirmation dialog), then asks for the password on every login.
- **Older clients**: classic chat commands — `/register <password> <confirm>`, `/login <password>`,
  `/logout` (aliases `/reg`, `/l`).
- Until logged in, players are frozen: no movement, chat, commands, block break/place,
  interaction, damage, hunger or pickups. 5 wrong attempts = kick.
- Password policy: 4–32 characters, no spaces.

## Build locally

Requirements: Java 21+, Maven, and a ViaVersion plugin jar (compile-only, never bundled).

```bash
mvn -B package -DskipTests -Dviaversion.jar=/path/to/ViaVersion.jar
# jar -> target/SimpleLogin-<version>.jar
```

## Release (publishes the jar XeltSrv downloads)

```bash
git tag v1.0.0
git push origin v1.0.0
```

Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds the jar and attaches it
to a GitHub Release with the same name. XeltSrv's `starter.py` downloads
`SimpleLogin-<version>.jar` from the latest release (`SIMPLELOGIN_REPO` constant).

## Version matrix

| SimpleLogin | Paper      | Java |
|-------------|------------|------|
| 1.0.x       | 26.2.x     | 21+  |
