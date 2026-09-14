package gg.xelt.simplelogin;

import org.bukkit.plugin.java.JavaPlugin;

/** SimpleLogin: local login with 1.21.6+ dialogs, chat commands for older clients. */
public final class SimpleLogin extends JavaPlugin {

    private UserStore users;
    private AuthManager auth;

    @Override
    public void onEnable() {
        users = new UserStore(this);
        users.load();
        auth = new AuthManager(this, users);
        getServer().getPluginManager().registerEvents(new LoginListener(this), this);
        LoginCommands commands = new LoginCommands(this);
        getCommand("login").setExecutor(commands);
        getCommand("register").setExecutor(commands);
        getCommand("logout").setExecutor(commands);
        if (getServer().getPluginManager().getPlugin("ViaVersion") != null) {
            getLogger().info("ViaVersion detected: 1.21.6+ clients will get dialogs.");
        } else {
            getLogger().warning("ViaVersion not found: all clients will use chat commands.");
        }
        getLogger().info("SimpleLogin enabled.");
    }

    @Override
    public void onDisable() {
        getLogger().info("SimpleLogin disabled.");
    }

    public UserStore users() {
        return users;
    }

    public AuthManager auth() {
        return auth;
    }
}
