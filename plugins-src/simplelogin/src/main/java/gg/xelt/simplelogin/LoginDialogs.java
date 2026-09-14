package gg.xelt.simplelogin;

import io.papermc.paper.dialog.Dialog;
import io.papermc.paper.registry.data.dialog.ActionButton;
import io.papermc.paper.registry.data.dialog.DialogBase;
import io.papermc.paper.registry.data.dialog.action.DialogAction;
import io.papermc.paper.registry.data.dialog.action.DialogActionCallback;
import io.papermc.paper.registry.data.dialog.body.DialogBody;
import io.papermc.paper.registry.data.dialog.input.DialogInput;
import io.papermc.paper.registry.data.dialog.type.DialogType;
import java.time.Duration;
import java.util.List;
import net.kyori.adventure.text.Component;
import net.kyori.adventure.text.event.ClickCallback;
import net.kyori.adventure.text.format.NamedTextColor;
import net.kyori.adventure.text.format.TextDecoration;
import org.bukkit.Bukkit;
import org.bukkit.entity.Player;

/** Builds the 1.21.6+ login/register dialogs. A fresh dialog is built per attempt. */
public final class LoginDialogs {

    private static final String KEY = "password";

    private LoginDialogs() {
    }

    public static void show(SimpleLogin plugin, Player player, AuthManager.Stage stage) {
        if (stage == null) {
            return;
        }
        Dialog dialog = switch (stage) {
            case REGISTER_PASSWORD -> build(plugin,
                    "Crear cuenta",
                    "Escribe una contraseña para registrarte (" + AuthManager.MIN_LEN + "-" + AuthManager.MAX_LEN + " caracteres, sin espacios).",
                    "Continuar");
            case REGISTER_CONFIRM -> build(plugin,
                    "Confirmar contraseña",
                    "Repite la misma contraseña para confirmar el registro.",
                    "Confirmar");
            case LOGIN -> build(plugin,
                    "Iniciar sesión",
                    "Escribe tu contraseña para entrar al servidor.",
                    "Entrar");
        };
        player.showDialog(dialog);
    }

    private static Dialog build(SimpleLogin plugin, String title, String body, String confirmLabel) {
        DialogActionCallback submit = (response, audience) -> {
            if (!(audience instanceof Player player)) {
                return;
            }
            String value = response == null ? null : response.getText(KEY);
            AuthManager.Stage stage = plugin.auth().stageOf(player);
            // Dialog callbacks may arrive off-thread: get back on the main thread.
            if (Bukkit.isPrimaryThread()) {
                plugin.auth().handleDialogInput(player, stage, value);
            } else {
                Bukkit.getScheduler().runTask(plugin, () ->
                        plugin.auth().handleDialogInput(player, stage, value));
            }
        };
        DialogActionCallback reshow = (response, audience) -> {
            if (!(audience instanceof Player player)) {
                return;
            }
            Runnable task = () -> plugin.auth().showPrompt(player);
            if (Bukkit.isPrimaryThread()) {
                task.run();
            } else {
                Bukkit.getScheduler().runTask(plugin, task);
            }
        };
        ActionButton yes = ActionButton.builder(Component.text(confirmLabel, NamedTextColor.GREEN, TextDecoration.BOLD))
                .action(DialogAction.customClick(submit, ClickCallback.Options.builder()
                        .uses(1)
                        .lifetime(Duration.ofMinutes(10))
                        .build()))
                .width(200)
                .build();
        ActionButton no = ActionButton.builder(Component.text("Cancelar", NamedTextColor.GRAY))
                .action(DialogAction.customClick(reshow, ClickCallback.Options.builder()
                        .uses(1)
                        .lifetime(Duration.ofMinutes(10))
                        .build()))
                .width(200)
                .build();
        return Dialog.create(factory -> factory.empty()
                .base(DialogBase.builder(Component.text(title, NamedTextColor.GOLD, TextDecoration.BOLD))
                        .body(List.of(DialogBody.plainMessage(Component.text(body, NamedTextColor.WHITE))))
                        .inputs(List.of(DialogInput.text(KEY, Component.text("Contraseña"))
                                .width(200)
                                .maxLength(AuthManager.MAX_LEN)
                                .initial("")
                                .build()))
                        .canCloseWithEscape(false)
                        .afterAction(DialogBase.DialogAfterAction.CLOSE)
                        .build())
                .type(DialogType.confirmation(yes, no)));
    }
}
