package gg.xelt.simplelogin;

import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.format.NamedTextColor;
import org.bukkit.command.Command;
import org.bukkit.command.CommandExecutor;
import org.bukkit.command.CommandSender;
import org.bukkit.entity.Player;

/** /login, /register and /logout for clients without dialog support. */
public final class LoginCommands implements CommandExecutor {

    private final SimpleLogin plugin;

    public LoginCommands(SimpleLogin plugin) {
        this.plugin = plugin;
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(Component.text("Solo los jugadores pueden usar este comando.", NamedTextColor.RED));
            return true;
        }
        String name = command.getName().toLowerCase();
        switch (name) {
            case "login", "l" -> {
                if (args.length != 1) {
                    player.sendMessage(Component.text("Uso: /login <contraseña>", NamedTextColor.YELLOW));
                    return true;
                }
                plugin.auth().loginCommand(player, args[0]);
            }
            case "register", "reg" -> {
                if (args.length != 2) {
                    player.sendMessage(Component.text("Uso: /register <contraseña> <confirmar>", NamedTextColor.YELLOW));
                    return true;
                }
                plugin.auth().registerCommand(player, args[0], args[1]);
            }
            case "logout" -> {
                if (plugin.auth().isAuthenticated(player)) {
                    plugin.auth().logout(player);
                } else {
                    player.sendMessage(Component.text("No tienes la sesión iniciada.", NamedTextColor.RED));
                }
            }
            default -> {
                return false;
            }
        }
        return true;
    }
}
