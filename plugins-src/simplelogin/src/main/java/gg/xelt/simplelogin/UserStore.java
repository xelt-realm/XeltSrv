package gg.xelt.simplelogin;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Locale;
import org.bukkit.configuration.file.YamlConfiguration;

/** Local password storage (users.yml) with salted SHA-256 hashes. */
public final class UserStore {

    private final SimpleLogin plugin;
    private final java.io.File file;
    private YamlConfiguration data;

    public UserStore(SimpleLogin plugin) {
        this.plugin = plugin;
        this.file = new java.io.File(plugin.getDataFolder(), "users.yml");
    }

    public void load() {
        if (!plugin.getDataFolder().exists()) {
            plugin.getDataFolder().mkdirs();
        }
        data = YamlConfiguration.loadConfiguration(file);
    }

    public void save() {
        try {
            data.save(file);
        } catch (Exception e) {
            plugin.getLogger().warning("Could not save users.yml: " + e.getMessage());
        }
    }

    private static String key(String name) {
        return "users." + name.toLowerCase(Locale.ROOT);
    }

    public boolean isRegistered(String name) {
        return data.contains(key(name) + ".hash");
    }

    public void register(String name, String password) {
        String salt = randomHex(16);
        data.set(key(name) + ".name", name);
        data.set(key(name) + ".salt", salt);
        data.set(key(name) + ".hash", sha256Hex(salt + password));
        save();
    }

    public boolean check(String name, String password) {
        String k = key(name);
        String salt = data.getString(k + ".salt", "");
        String expected = data.getString(k + ".hash", "");
        if (salt.isEmpty() || expected.isEmpty()) {
            return false;
        }
        String actual = sha256Hex(salt + password);
        return MessageDigest.isEqual(
                actual.getBytes(StandardCharsets.UTF_8),
                expected.getBytes(StandardCharsets.UTF_8));
    }

    private static String randomHex(int bytes) {
        byte[] b = new byte[bytes];
        new SecureRandom().nextBytes(b);
        StringBuilder sb = new StringBuilder(b.length * 2);
        for (byte x : b) {
            sb.append(String.format("%02x", x));
        }
        return sb.toString();
    }

    private static String sha256Hex(String input) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder(digest.length * 2);
            for (byte x : digest) {
                sb.append(String.format("%02x", x));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 not available", e);
        }
    }
}
