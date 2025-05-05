import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from utils.utils import is_admin, salon_est_autorise, log_erreur

# → chemins vers les JSON
MISSIONS_PATH  = "/data/missions_du_jour.json"
CONSEILS_PATH  = "/data/conseils_methodo.json"

def charger_liste(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_liste(path: str, data: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

class AjouterElementModal(discord.ui.Modal):
    def __init__(self, bot, path, label, titre, element_type):
        super().__init__(title=titre)
        self.bot = bot; self.path = path; self.element_type = element_type
        self.contenu = discord.ui.TextInput(label=label, style=discord.TextStyle.paragraph)
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            items = charger_liste(self.path)
            items.append(self.contenu.value)
            sauvegarder_liste(self.path, items)
            await interaction.response.send_message(f"✅ {self.element_type} ajoutée !", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"AjouterElementModal: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'ajout.", ephemeral=True)

class ModifierElementModal(discord.ui.Modal):
    def __init__(self, bot, path, index, ancien, element_type):
        super().__init__(title=f"Modifier {element_type}")
        self.bot = bot; self.path = path; self.index = index; self.element_type = element_type
        self.contenu = discord.ui.TextInput(
            label=f"{element_type} #{index}", style=discord.TextStyle.paragraph, default=ancien
        )
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            items = charger_liste(self.path)
            items[self.index] = self.contenu.value
            sauvegarder_liste(self.path, items)
            await interaction.response.send_message(f"✅ {self.element_type} modifié !", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ModifierElementModal: {e}")
            await interaction.response.send_message("❌ Erreur lors de la modification.", ephemeral=True)

class Missions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def check_admin_salon(self, interaction: discord.Interaction, cmd: str) -> bool:
        if not await is_admin(interaction.user):
            await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            return False
        if not salon_est_autorise(cmd, interaction.channel_id, interaction.user):
            await interaction.response.send_message("❌ Commande non autorisée ici.", ephemeral=True)
            return False
        return True

    # ==== MISSIONS ====

    @app_commands.command(name="ajouter_mission", description="Ajoute une mission du jour.")
    @app_commands.default_permissions(kick_members=True)
    async def ajouter_mission(self, interaction: discord.Interaction):
        if not await self.check_admin_salon(interaction, "ajouter_mission"):
            return
        await interaction.response.send_modal(
            AjouterElementModal(self.bot, MISSIONS_PATH, "Mission", "Nouvelle mission", "Mission")
        )

    @app_commands.command(name="modifier_mission", description="Modifie une mission du jour.")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(index="Index de la mission à modifier (voir /voir_missions)")
    async def modifier_mission(self, interaction: discord.Interaction, index: int):
        if not await self.check_admin_salon(interaction, "modifier_mission"):
            return
        data = charger_liste(MISSIONS_PATH)
        if 0 <= index < len(data):
            await interaction.response.send_modal(
                ModifierElementModal(self.bot, MISSIONS_PATH, index, data[index], "Mission")
            )
        else:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

    @modifier_mission.autocomplete("index")
    async def modifier_mission_autocomplete(self, interaction: discord.Interaction, current: str):
        data = charger_liste(MISSIONS_PATH)
        choices = [
            app_commands.Choice(name=f"{i}. {m}", value=i)
            for i, m in enumerate(data)
            if current in str(i) or current.lower() in m.lower()
        ]
        return choices[:25]

    @app_commands.command(name="supprimer_mission", description="Supprime une mission du jour.")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(index="Index de la mission à supprimer (voir /voir_missions)")
    async def supprimer_mission(self, interaction: discord.Interaction, index: int):
        if not await self.check_admin_salon(interaction, "supprimer_mission"):
            return
        data = charger_liste(MISSIONS_PATH)
        if 0 <= index < len(data):
            removed = data.pop(index)
            sauvegarder_liste(MISSIONS_PATH, data)
            await interaction.response.send_message(f"✅ Mission supprimée : **{removed}**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

    @supprimer_mission.autocomplete("index")
    async def supprimer_mission_autocomplete(self, interaction: discord.Interaction, current: str):
        data = charger_liste(MISSIONS_PATH)
        choices = [
            app_commands.Choice(name=f"{i}. {m}", value=i)
            for i, m in enumerate(data)
            if current in str(i) or current.lower() in m.lower()
        ]
        return choices[:25]

    @app_commands.command(name="voir_missions", description="Liste les missions actuelles.")
    @app_commands.default_permissions(kick_members=True)
    async def voir_missions(self, interaction: discord.Interaction):
        if not await self.check_admin_salon(interaction, "voir_missions"):
            return
        data = charger_liste(MISSIONS_PATH)
        if not data:
            return await interaction.response.send_message("ℹ️ Aucune mission définie.", ephemeral=True)
        texte = "\n".join(f"{i}. {m}" for i, m in enumerate(data))
        await interaction.response.send_message(f"📋 Missions du jour :\n{texte}", ephemeral=True)

    # ==== CONSEILS ====

    @app_commands.command(name="ajouter_conseil", description="Ajoute un conseil méthodo.")
    @app_commands.default_permissions(kick_members=True)
    async def ajouter_conseil(self, interaction: discord.Interaction):
        if not await self.check_admin_salon(interaction, "ajouter_conseil"):
            return
        await interaction.response.send_modal(
            AjouterElementModal(self.bot, CONSEILS_PATH, "Conseil", "Nouveau conseil", "Conseil")
        )

    @app_commands.command(name="modifier_conseil", description="Modifie un conseil méthodo.")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(index="Index du conseil à modifier (voir /voir_conseils)")
    async def modifier_conseil(self, interaction: discord.Interaction, index: int):
        if not await self.check_admin_salon(interaction, "modifier_conseil"):
            return
        data = charger_liste(CONSEILS_PATH)
        if 0 <= index < len(data):
            await interaction.response.send_modal(
                ModifierElementModal(self.bot, CONSEILS_PATH, index, data[index], "Conseil")
            )
        else:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

    @modifier_conseil.autocomplete("index")
    async def modifier_conseil_autocomplete(self, interaction: discord.Interaction, current: str):
        data = charger_liste(CONSEILS_PATH)
        choices = [
            app_commands.Choice(name=f"{i}. {c}", value=i)
            for i, c in enumerate(data)
            if current in str(i) or current.lower() in c.lower()
        ]
        return choices[:25]

    @app_commands.command(name="supprimer_conseil", description="Supprime un conseil méthodo.")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.describe(index="Index du conseil à supprimer (voir /voir_conseils)")
    async def supprimer_conseil(self, interaction: discord.Interaction, index: int):
        if not await self.check_admin_salon(interaction, "supprimer_conseil"):
            return
        data = charger_liste(CONSEILS_PATH)
        if 0 <= index < len(data):
            removed = data.pop(index)
            sauvegarder_liste(CONSEILS_PATH, data)
            await interaction.response.send_message(f"✅ Conseil supprimé : **{removed}**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

    @supprimer_conseil.autocomplete("index")
    async def supprimer_conseil_autocomplete(self, interaction: discord.Interaction, current: str):
        data = charger_liste(CONSEILS_PATH)
        choices = [
            app_commands.Choice(name=f"{i}. {c}", value=i)
            for i, c in enumerate(data)
            if current in str(i) or current.lower() in c.lower()
        ]
        return choices[:25]

async def setup(bot):
    await bot.add_cog(Missions(bot))
