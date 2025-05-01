import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime, timedelta
from utils.utils import is_verified_user, is_admin, salon_est_autorise, log_erreur

DATA_PATH = "data/checkin_humeurs.json"

def charger_donnees():
    if not os.path.exists(DATA_PATH):
        return {}
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sauvegarder_donnees(data):
    os.makedirs("data", exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

class CheckinModal(discord.ui.Modal, title="Check-in Humeur (0 à 10)"):
    humeur = discord.ui.TextInput(
        label="Quelle est ton humeur aujourd’hui ?",
        placeholder="Sur une échelle de 0 (très mal) à 10 (au top)",
        required=True,
        max_length=2
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = charger_donnees()
            user_id = str(interaction.user.id)
            try:
                score = int(self.humeur.value.strip())
                if not 0 <= score <= 10:
                    raise ValueError
            except ValueError:
                return await interaction.response.send_message("❌ Merci d'entrer un nombre entre 0 et 10.", ephemeral=True)

            entry = {"date": datetime.utcnow().isoformat(), "score": score}
            data.setdefault(user_id, []).append(entry)
            sauvegarder_donnees(data)
            await interaction.response.send_message("✅ Humeur enregistrée avec succès !", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"CheckinModal: {e}")
            await interaction.response.send_message("❌ Erreur lors de l'enregistrement.", ephemeral=True)

class Checkin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="checkin", description="Note ton humeur du jour (0 à 10)")
    async def checkin(self, interaction: discord.Interaction):
        if not await is_verified_user(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux membres vérifiés.", ephemeral=True)
        if not salon_est_autorise("checkin", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée ici.", ephemeral=True)
        await interaction.response.send_modal(CheckinModal())

    @app_commands.command(name="humeur_utilisateur", description="Voir l’historique d’humeur d’un utilisateur (staff uniquement)")
    async def humeur_utilisateur(self, interaction: discord.Interaction, membre: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        data = charger_donnees()
        user_id = str(membre.id)
        if user_id not in data:
            return await interaction.response.send_message("ℹ️ Aucun check-in trouvé pour cet utilisateur.", ephemeral=True)

        now = datetime.utcnow()
        valeurs = data[user_id]

        def moyenne_sur(interval):
            limite = now - timedelta(days=interval)
            scores = [entry["score"] for entry in valeurs if datetime.fromisoformat(entry["date"]) >= limite]
            return round(sum(scores) / len(scores), 2) if scores else "Aucune donnée"

        moyenne_jour = valeurs[-1]["score"]
        moyenne_7j = moyenne_sur(7)
        moyenne_30j = moyenne_sur(30)

        embed = discord.Embed(title=f"Humeur de {membre.display_name}", color=discord.Color.orange())
        embed.add_field(name="📅 Aujourd'hui", value=str(moyenne_jour), inline=True)
        embed.add_field(name="📆 Moyenne 7 jours", value=str(moyenne_7j), inline=True)
        embed.add_field(name="📅 Moyenne 30 jours", value=str(moyenne_30j), inline=True)
        embed.set_footer(text="Source : /checkin")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Checkin(bot))
