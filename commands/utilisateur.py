import discord
from discord import app_commands
from discord.ext import commands
import random
from utils.utils import salon_est_autorise, get_or_create_role, get_or_create_category


class UtilisateurCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Conseils pour /conseil_aleatoire
        self.conseils = [
            "🧠 Répète tes cours à haute voix comme si tu les expliquais à quelqu’un.",
            "⏱️ Utilise la méthode Pomodoro pour gérer ton temps de travail.",
            "📚 Teste-toi sur des QCM plutôt que de relire passivement.",
            "📝 Fais des fiches synthétiques par thème au lieu de suivre l'ordre des chapitres.",
            "🤝 Échange avec tes camarades, enseigner est la meilleure façon d'apprendre."
        ]

    # /conseil_methodo
    @app_commands.command(name="conseil_methodo", description="Pose une question méthodo (public).")
    @app_commands.describe(question="Quelle est ta question méthodo ?")
    async def conseil_methodo(self, interaction: discord.Interaction, question: str):
        if not salon_est_autorise("conseil_methodo", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        embed = discord.Embed(
            title="Nouvelle question méthodo",
            description=question,
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"Posée par {interaction.user.display_name}")
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Ta question a été envoyée !", ephemeral=True)

    # /conseil_aleatoire
    @app_commands.command(name="conseil_aleatoire", description="Donne un conseil de travail aléatoire.")
    async def conseil_aleatoire(self, interaction: discord.Interaction):
        if not salon_est_autorise("conseil_aleatoire", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        conseil = random.choice(self.conseils)
        await interaction.response.send_message(f"💡 Conseil : **{conseil}**", ephemeral=True)

    # /ressources
    @app_commands.command(name="ressources", description="Liste des ressources utiles.")
    async def ressources(self, interaction: discord.Interaction):
        if not salon_est_autorise("ressources", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        embed = discord.Embed(
            title="Ressources utiles",
            description="Voici quelques liens et documents qui pourraient t'aider :",
            color=discord.Color.green()
        )
        embed.add_field(name="🔗 Fiches Méthodo", value="[Accéder](https://exemple.com/fiches)", inline=False)
        embed.add_field(name="📝 Tableur de planning", value="[Google Sheets](https://docs.google.com)", inline=False)
        embed.add_field(name="🎧 Podcast Motivation", value="[Podcast X](https://podcast.com)", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /mission_du_jour
    @app_commands.command(name="mission_du_jour", description="Obtiens un mini-défi pour la journée.")
    async def mission_du_jour(self, interaction: discord.Interaction):
        if not salon_est_autorise("mission_du_jour", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        missions = [
            "📵 Évite les réseaux sociaux jusqu'à 20h.",
            "🧘‍♂️ Fais 5 min de respiration avant de commencer à réviser.",
            "📖 Relis 2 fiches avant le coucher.",
            "💌 Envoie un message d’encouragement à un camarade.",
            "🧹 Range ton espace de travail pour gagner en clarté."
        ]
        await interaction.response.send_message(f"🎯 Mission du jour : **{random.choice(missions)}**", ephemeral=True)

    # /checkin
    @app_commands.command(name="checkin", description="Exprime ton humeur avec un emoji.")
    @app_commands.describe(humeur="Ex: 😀, 😞, 😴, etc.")
    async def checkin(self, interaction: discord.Interaction, humeur: str):
        if not salon_est_autorise("checkin", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        await interaction.response.send_message(f"📌 Humeur enregistrée : {humeur}", ephemeral=True)

    

async def setup_user_commands(bot):
    await bot.add_cog(UtilisateurCommands(bot))
