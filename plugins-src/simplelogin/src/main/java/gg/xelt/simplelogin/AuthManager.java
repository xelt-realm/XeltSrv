package gg.xelt.simplelogin;

import com.viaversion.viaversion.api.Via;
import com.viaversion.viaversion.api.protocol.version.ProtocolVersion;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;
import org.bukkit.scheduler.BukkitTask;

/** Tracks who still needs to log in and drives the dialog/chat prompts. */
public final class AuthManager {

    public enum Stage { REGISTER_PASSWORD, REGISTER_CONFIRM, LOGIN }

    public static final int MIN_LEN = 4;
    public static final int MAX_LEN = 32;
    public static final int MAX_ATTEMPTS = 5;

    private static final int PROTOCOL_1_21_6 = resolveProtocol();

    private final SimpleLogin plugin;
    private final UserStore users;
    private final Set<UUID> authenticated = new HashSet<>();
    private final Map<UUID, Stage> pendingStage = new HashMap<>();
    private final Map<UUID, String> pendingPassword = new HashMap<>();
    private final Map<UUID, Integer> attempts = new HashMap<>();
    private final Map<UUID, BukkitTask> reminders = new HashMap<>();

    public AuthManager(SimpleLogin plugin, UserStore users) {
        this.plugin = plugin;
        this.users = users;
    }

    private static int resolveProtocol() {
        try {
            return ProtocolVersion.v1_21_6.getVersion();
        } catch (Throwable t) {
            return 771; // 1.21.6
        }
    }

    /** True when the client speaks 1.21.6+ (dialogs supported). */
    public boolean supportsDialog(Player player) {
        try {
            if (Bukkit.getPluginManager().getPlugin("ViaVersion") == null) {
                return false;
            }
            return Via.getAPI().getPlayerVersion(player.getUniqueId()) >= PROTOCOL_1_21_6;
        } catch (Throwable t) {
            return false;
        }
    }

    public boolean isAuthenticated(Player player) {
        return authenticated.contains(player.getUniqueId());
    }

    public boolean needsLogin(Player player) {
        return !isAuthenticated(player);
    }

    public Stage stageOf(Player player) {
        return pendingStage.get(player.getUniqueId());
    }

    /** Called on join: freeze + schedule the prompt strictly after entering the game. */
    public void beginSession(Player player) {
        UUID id = player.getUniqueId();
        authenticated.remove(id);
        attempts.remove(id);
        pendingPassword.remove(id);
        pendingStage.put(id, users.isRegistered(player.getName()) ? Stage.LOGIN : Stage.REGISTER_PASSWORD);
        // Show the prompt once the player is fully in-game.
        Bukkit.getScheduler().runTaskLater(plugin, () -> {
            if (player.isOnline() && needsLogin(player)) {
                showPrompt(player);
            }
        }, 30L);
        cancelReminder(id);
        reminders.put(id, Bukkit.getScheduler().runTaskTimer(plugin, () -> {
            if (player.isOnline() && needsLogin(player)) {
                sendHowTo(player);
            } else {
                cancelReminder(id);
            }
        }, 300L, 300L));
    }

    public void endSession(Player player) {
        UUID id = player.getUniqueId();
        authenticated.remove(id);
        pendingStage.remove(id);
        pendingPassword.remove(id);
        attempts.remove(id);
        cancelReminder(id);
    }

    private void cancelReminder(UUID id) {
        BukkitTask task = reminders.remove(id);
        if (task != null) {
            task.cancel();
        }
    }

    public void logout(Player player) {
        authenticated.remove(player.getUniqueId());
        attempts.remove(player.getUniqueId());
        pendingPassword.remove(player.getUniqueId());
        pendingStage.put(player.getUniqueId(),
                users.isRegistered(player.getName()) ? Stage.LOGIN : Stage.REGISTER_PASSWORD);
        player.sendMessage(Component.text("Sesión cerrada. Vuelve a identificarte.", NamedTextColor.YELLOW));
        showPrompt(player);
    }

    public void showPrompt(Player player) {
        if (!player.isOnline() || isAuthenticated(player)) {
            return;
        }
        if (supportsDialog(player)) {
            LoginDialogs.show(plugin, player, pendingStage.get(player.getUniqueId()));
        } else {
            sendHowTo(player);
        }
    }

    private void sendHowTo(Player player) {
        if (users.isRegistered(player.getName())) {
            player.sendMessage(Component.text("Usa /login <contraseña> para entrar.", NamedTextColor.GOLD));
        } else {
            player.sendMessage(Component.text("Usa /register <contraseña> <confirmar> para crear tu cuenta.", NamedTextColor.GOLD));
        }
    }

    /** Password policy shared by dialogs and commands. Null = valid. */
    public static String validate(String password) {
        if (password == null || password.length() < MIN_LEN) {
            return "La contraseña debe tener al menos " + MIN_LEN + " caracteres.";
        }
        if (password.length() > MAX_LEN) {
            return "La contraseña debe tener como máximo " + MAX_LEN + " caracteres.";
        }
        if (password.contains(" ")) {
            return "La contraseña no puede contener espacios.";
        }
        return null;
    }

    /** Input coming from a dialog (already validated length-wise where needed). */
    public void handleDialogInput(Player player, Stage stage, String value) {
        if (!player.isOnline() || isAuthenticated(player)) {
            return;
        }
        if (value == null || value.isEmpty()) {
            player.sendMessage(Component.text("Escribe tu contraseña.", NamedTextColor.RED));
            showPrompt(player);
            return;
        }
        switch (stage) {
            case REGISTER_PASSWORD -> {
                String err = validate(value);
                if (err != null) {
                    player.sendMessage(Component.text(err, NamedTextColor.RED));
                    showPrompt(player);
                    return;
                }
                pendingPassword.put(player.getUniqueId(), value);
                pendingStage.put(player.getUniqueId(), Stage.REGISTER_CONFIRM);
                LoginDialogs.show(plugin, player, Stage.REGISTER_CONFIRM);
            }
            case REGISTER_CONFIRM -> {
                String first = pendingPassword.get(player.getUniqueId());
                if (first != null && first.equals(value)) {
                    users.register(player.getName(), value);
                    pendingPassword.remove(player.getUniqueId());
                    authenticate(player, "¡Cuenta creada! Bienvenido/a.");
                } else {
                    pendingPassword.remove(player.getUniqueId());
                    pendingStage.put(player.getUniqueId(), Stage.REGISTER_PASSWORD);
                    player.sendMessage(Component.text("Las contraseñas no coinciden. Empieza de nuevo.", NamedTextColor.RED));
                    LoginDialogs.show(plugin, player, Stage.REGISTER_PASSWORD);
                }
            }
            case LOGIN -> {
                if (users.check(player.getName(), value)) {
                    authenticate(player, "¡Sesión iniciada! Bienvenido/a de nuevo.");
                } else {
                    wrongAttempt(player);
                }
            }
        }
    }

    /** Chat command /login. */
    public void loginCommand(Player player, String password) {
        if (isAuthenticated(player)) {
            player.sendMessage(Component.text("Ya tienes la sesión iniciada.", NamedTextColor.GREEN));
            return;
        }
        if (!users.isRegistered(player.getName())) {
            player.sendMessage(Component.text("No tienes cuenta. Usa /register <contraseña> <confirmar>.", NamedTextColor.RED));
            return;
        }
        if (users.check(player.getName(), password)) {
            authenticate(player, "¡Sesión iniciada! Bienvenido/a de nuevo.");
        } else {
            wrongAttempt(player);
        }
    }

    /** Chat command /register. */
    public void registerCommand(Player player, String password, String confirm) {
        if (isAuthenticated(player)) {
            player.sendMessage(Component.text("Ya tienes la sesión iniciada.", NamedTextColor.GREEN));
            return;
        }
        if (users.isRegistered(player.getName())) {
            player.sendMessage(Component.text("Ya tienes cuenta. Usa /login <contraseña>.", NamedTextColor.RED));
            return;
        }
        String err = validate(password);
        if (err != null) {
            player.sendMessage(Component.text(err, NamedTextColor.RED));
            return;
        }
        if (!password.equals(confirm)) {
            player.sendMessage(Component.text("Las contraseñas no coinciden.", NamedTextColor.RED));
            return;
        }
        users.register(player.getName(), password);
        authenticate(player, "¡Cuenta creada! Bienvenido/a.");
    }

    private void wrongAttempt(Player player) {
        int n = attempts.merge(player.getUniqueId(), 1, Integer::sum);
        if (n >= MAX_ATTEMPTS) {
            player.kick(Component.text("Demasiados intentos. Vuelve a intentarlo.", NamedTextColor.RED));
            return;
        }
        player.sendMessage(Component.text(
                "Contraseña incorrecta (" + n + "/" + MAX_ATTEMPTS + ").", NamedTextColor.RED));
        showPrompt(player);
    }

    private void authenticate(Player player, String welcome) {
        authenticated.add(player.getUniqueId());
        pendingStage.remove(player.getUniqueId());
        pendingPassword.remove(player.getUniqueId());
        attempts.remove(player.getUniqueId());
        cancelReminder(player.getUniqueId());
        player.closeDialog();
        player.sendMessage(Component.text(welcome, NamedTextColor.GREEN));
    }
}
