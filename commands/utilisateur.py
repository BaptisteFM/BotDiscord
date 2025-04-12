import discord
from discord import app_commands
from discord.ext import commands
import random
from utils.utils import salon_est_autorise, get_or_create_role, get_or_create_category

class UtilisateurCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Liste de conseils pour la commande /conseil_aleatoire
        self.conseils = [
            "🧠 Répète tes cours à haute voix comme si tu les expliquais à quelqu’un.",
            "⏱️ Utilise la méthode Pomodoro pour gérer ton temps de travail.",
            "📚 Teste-toi sur des QCM plutôt que de relire passivement.",
            "📝 Fais des fiches synthétiques par thème plutôt que par ordre de cours.",
            "🤝 Échange avec tes camarades – enseigner est la meilleure façon d'apprendre."
        ]

    # -------------------------------
    # Commande: /conseil_methodo
    # Description: Pose une question méthodo (public).
    # -------------------------------
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

    # -------------------------------
    # Commande: /conseil_aleatoire
    # Description: Donne un conseil de travail aléatoire.
    # -------------------------------
    @app_commands.command(name="conseil_aleatoire", description="Donne un conseil de travail aléatoire.")
    async def conseil_aleatoire(self, interaction: discord.Interaction):
        if not salon_est_autorise("conseil_aleatoire", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
        conseil = random.choice(self.conseils)
        await interaction.response.send_message(f"💡 Conseil : **{conseil}**", ephemeral=True)

    # -------------------------------
    # Commande: /ressources
    # Description: Affiche une liste de ressources utiles.
    # -------------------------------
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

    # -------------------------------
    # Commande: /mission_du_jour
    # Description: Propose un mini-défi pour la journée.
    # -------------------------------
    @app_commands.command(name="mission_du_jour", description="Obtiens un mini-défi pour la journée.")
    async def mission_du_jour(self, interaction: discord.Interaction):
        if not salon_est_autorise("mission_du_jour", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
        missions = [
            "📵 Évite les réseaux sociaux jusqu'à 20h.",
            "🧘‍♂️ Fais 5 min de respiration avant de réviser.",
            "📖 Relis 2 fiches avant le coucher.",
            "💌 Envoie un message d'encouragement à un camarade.",
            "🧹 Range ton espace de travail pour gagner en clarté."
        ]
        await interaction.response.send_message(f"🎯 Mission du jour : **{random.choice(missions)}**", ephemeral=True)

    # -------------------------------
    # Commande: /checkin
    # Description: Permet d'exprimer son humeur avec un emoji.
    # -------------------------------
    @app_commands.command(name="checkin", description="Exprime ton humeur avec un emoji.")
    @app_commands.describe(humeur="Ex: 😀, 😞, 😴, etc.")
    async def checkin(self, interaction: discord.Interaction, humeur: str):
        if not salon_est_autorise("checkin", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
        await interaction.response.send_message(f"📌 Humeur enregistrée : {humeur}", ephemeral=True)

    # -------------------------------
    # Commande: /cours_aide
    # Description: Demande d'aide sur un cours via modal.
    # -------------------------------
    @app_commands.command(name="cours_aide", description="Demande d'aide sur un cours via modal.")
    async def cours_aide(self, interaction: discord.Interaction):
        if not salon_est_autorise("cours_aide", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        # Définition du modal pour recueillir la demande d'aide sur un cours
        class CoursAideModal(discord.ui.Modal, title="Demande d'aide sur un cours"):
            cours = discord.ui.TextInput(
                label="Cours concerné",
                placeholder="Ex : Mathématiques, Physique, etc.",
                required=True
            )
            details = discord.ui.TextInput(
                label="Détaillez votre problème",
                style=discord.TextStyle.paragraph,
                placeholder="Expliquez précisément ce que vous n'avez pas compris.",
                required=True
            )
            async def on_submit(modal_interaction: discord.Interaction):
                user = modal_interaction.user
                guild = modal_interaction.guild

                # Créer un rôle temporaire pour le demandeur et l'ajouter
                temp_role = await get_or_create_role(guild, f"CoursAide-{user.name}")
                await user.add_roles(temp_role)

                # Récupérer le rôle d'aide défini par admin via la config (option "role_aide")
                from utils.utils import charger_config
                config = charger_config()
                role_aide_id = config.get("role_aide")  # L'admin doit configurer cette option
                role_aide = guild.get_role(int(role_aide_id)) if role_aide_id else None

                # Définir les permissions : accès autorisé pour le rôle temporaire et, si défini, le rôle d'aide
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    temp_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                }
                if role_aide:
                    overwrites[role_aide] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                # Créer une catégorie privée dédiée à cette demande d'aide
                category = await guild.create_category(f"cours-aide-{user.name}".lower(), overwrites=overwrites)
                # Créer automatiquement un salon textuel et un salon vocal dans cette catégorie
                discussion_channel = await guild.create_text_channel("discussion", category=category)
                await guild.create_voice_channel("support-voice", category=category)
                # Dans le salon textuel, ping le rôle d'aide si défini
                if role_aide:
                    await discussion_channel.send(f"🔔 {role_aide.mention} une demande d'aide a été créée par {user.mention} !")
                    
                # Préparer l'embed à envoyer dans le salon où la commande a été lancée
                description = f"**Cours :** {self.cours.value}\n**Détails :** {self.details.value}"
                embed = discord.Embed(title="Demande d'aide sur un cours", description=description, color=discord.Color.blue())
                embed.set_footer(text=f"Demandée par {user.display_name}")
                
                # Créer la vue avec les boutons
                view = CoursAideView(user, category, temp_role)
                await modal_interaction.response.send_message(embed=embed, view=view)

        # Définition de la vue avec boutons pour la commande /cours_aide
        class CoursAideView(discord.ui.View):
            def __init__(self, demandeur: discord.Member, category: discord.CategoryChannel, temp_role: discord.Role):
                super().__init__(timeout=None)
                self.demandeur = demandeur
                self.category = category
                self.temp_role = temp_role

            @discord.ui.button(label="J'ai aussi ce problème", style=discord.ButtonStyle.primary, custom_id="btn_probleme")
            async def probleme_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                # Ajouter le rôle temporaire à l'utilisateur s'il ne l'a pas déjà
                if self.temp_role not in interaction.user.roles:
                    await interaction.user.add_roles(self.temp_role)
                    await interaction.response.send_message("✅ Vous avez rejoint cette demande d'aide.", ephemeral=True)
                else:
                    await interaction.response.send_message("ℹ️ Vous êtes déjà associé à cette demande.", ephemeral=True)

            @discord.ui.button(label="Supprimer la demande", style=discord.ButtonStyle.danger, custom_id="btn_supprimer")
            async def supprimer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != self.demandeur:
                    return await interaction.response.send_message("❌ Seul le demandeur peut supprimer cette demande.", ephemeral=True)
                try:
                    await self.category.delete()
                except Exception as e:
                    return await interaction.response.send_message(f"❌ Erreur lors de la suppression de la catégorie : {e}", ephemeral=True)
                try:
                    await self.demandeur.remove_roles(self.temp_role)
                except Exception as e:
                    return await interaction.response.send_message(f"❌ Erreur lors du retrait du rôle : {e}", ephemeral=True)
                await interaction.response.send_message("✅ Demande supprimée ; la catégorie privée et le rôle temporaire ont été retirés.", ephemeral=True)

        # Afficher le modal pour la commande /cours_aide
        await interaction.response.send_modal(CoursAideModal())

async def setup_user_commands(bot):
    await bot.add_cog(UtilisateurCommands(bot))
