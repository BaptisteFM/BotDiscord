import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from utils.utils import is_admin, salon_est_autorise, log_erreur

MISSIONS_PATH = "data/missions_du_jour.json"
CONSEILS_PATH = "data/conseils_methodo.json"

def charger_liste(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_liste(path, data):
    os.makedirs("data", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

class AjouterElementModal(discord.ui.Modal):
    def __init__(self, bot, path, label, titre, element_type):
        super().__init__(title=titre)
        self.path = path
        self.bot = bot
        self.element_type = element_type
        self.contenu = discord.ui.TextInput(label=label, style=discord.TextStyle.paragraph, required=True)
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            liste = charger_liste(self.path)
            liste.append(self.contenu.value)
            sauvegarder_liste(self.path, liste)
            await interaction.response.send_message(f"✅ {self.element_type} ajouté avec succès !", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"AjouterElementModal error : {e}")
            await interaction.response.send_message("❌ Erreur lors de l'ajout.", ephemeral=True)

class ModifierElementModal(discord.ui.Modal):
    def __init__(self, bot, path, index, ancien_texte, element_type):
        super().__init__(title=f"Modifier {element_type}")
        self.path = path
        self.index = index
        self.bot = bot
        self.element_type = element_type
        self.contenu = discord.ui.TextInput(label=f"Modifier {element_type} #{index}", style=discord.TextStyle.paragraph, default=ancien_texte)
        self.add_item(self.contenu)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            liste = charger_liste(self.path)
            if 0 <= self.index < len(liste):
                liste[self.index] = self.contenu.value
                sauvegarder_liste(self.path, liste)
                await interaction.response.send_message(f"✅ {self.element_type} modifié !", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Index invalide.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ModifierElementModal error : {e}")
            await interaction.response.send_message("❌ Erreur lors de la modification.", ephemeral=True)

class Missions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def check_admin_salon(self, interaction: discord.Interaction, command_name: str):
        if not await is_admin(interaction.user):
            await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            return False
        if not salon_est_autorise(command_name, interaction.channel_id, interaction.user):
            await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
            return False
        return True

    # ==== COMMANDES MISSIONS ====

    @app_commands.command(name="ajouter_mission", description="Ajoute une mission du jour.")
    async def ajouter_mission(self, interaction: discord.Interaction):
        if not await self.check_admin_salon(interaction, "ajouter_mission"):
            return
        await interaction.response.send_modal(AjouterElementModal(self.bot, MISSIONS_PATH, "Mission", "Nouvelle mission", "Mission"))

    @app_commands.command(name="modifier_mission", description="Modifie une mission du jour.")
    async def modifier_mission(self, interaction: discord.Interaction, index: int):
        if not await self.check_admin_salon(interaction, "modifier_mission"):
            return
        missions = charger_liste(MISSIONS_PATH)
        if 0 <= index < len(missions):
            await interaction.response.send_modal(ModifierElementModal(self.bot, MISSIONS_PATH, index, missions[index], "Mission"))
        else:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

    @app_commands.command(name="supprimer_mission", description="Supprime une mission du jour.")
    async def supprimer_mission(self, interaction: discord.Interaction, index: int):
        if not await self.check_admin_salon(interaction, "supprimer_mission"):
            return
        missions = charger_liste(MISSIONS_PATH)
        if 0 <= index < len(missions):
            supprimée = missions.pop(index)
            sauvegarder_liste(MISSIONS_PATH, missions)
            await interaction.response.send_message(f"✅ Mission supprimée : {supprimée}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

    @app_commands.command(name="voir_missions", description="Liste les missions actuelles.")
    async def voir_missions(self, interaction: discord.Interaction):
        if not await self.check_admin_salon(interaction, "voir_missions"):
            return
        missions = charger_liste(MISSIONS_PATH)
        if not missions:
            await interaction.response.send_message("ℹ️ Aucune mission définie.", ephemeral=True)
            return
        text = "\n".join(f"{i}. {m}" for i, m in enumerate(missions))
        await interaction.response.send_message(f"📋 Missions du jour :\n{text}", ephemeral=True)

    # ==== COMMANDES CONSEILS ====

    @app_commands.command(name="ajouter_conseil", description="Ajoute un conseil méthodo.")
    async def ajouter_conseil(self, interaction: discord.Interaction):
        if not await self.check_admin_salon(interaction, "ajouter_conseil"):
            return
        await interaction.response.send_modal(AjouterElementModal(self.bot, CONSEILS_PATH, "Conseil", "Nouveau conseil", "Conseil"))

    @app_commands.command(name="modifier_conseil", description="Modifie un conseil méthodo.")
    async def modifier_conseil(self, interaction: discord.Interaction, index: int):
        if not await self.check_admin_salon(interaction, "modifier_conseil"):
            return
        conseils = charger_liste(CONSEILS_PATH)
        if 0 <= index < len(conseils):
            await interaction.response.send_modal(ModifierElementModal(self.bot, CONSEILS_PATH, index, conseils[index], "Conseil"))
        else:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

    @app_commands.command(name="supprimer_conseil", description="Supprime un conseil méthodo.")
    async def supprimer_conseil(self, interaction: discord.Interaction, index: int):
        if not await self.check_admin_salon(interaction, "supprimer_conseil"):
            return
        conseils = charger_liste(CONSEILS_PATH)
        if 0 <= index < len(conseils):
            supprimé = conseils.pop(index)
            sauvegarder_liste(CONSEILS_PATH, conseils)
            await interaction.response.send_message(f"✅ Conseil supprimé : {supprimé}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Index invalide.", ephemeral=True)

    @app_commands.command(name="voir_conseils", description="Liste les conseils méthodo.")
    async def voir_conseils(self, interaction: discord.Interaction):
        if not await self.check_admin_salon(interaction, "voir_conseils"):
            return
        conseils = charger_liste(CONSEILS_PATH)
        if not conseils:
            await interaction.response.send_message("ℹ️ Aucun conseil disponible.", ephemeral=True)
            return
        text = "\n".join(f"{i}. {c}" for i, c in enumerate(conseils))
        await interaction.response.send_message(f"📚 Conseils méthodo :\n{text}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Missions(bot))
