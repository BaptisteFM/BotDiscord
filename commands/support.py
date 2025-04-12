import discord
from discord import app_commands
from discord.ext import commands
import random
import datetime
from utils.utils import salon_est_autorise, is_admin, get_or_create_role, get_redirection, charger_config

class SupportCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ───────────── /besoin_d_aide ─────────────
    @app_commands.command(name="besoin_d_aide", description="Décris ton besoin, un espace privé sera créé automatiquement.")
    async def besoin_d_aide(self, interaction: discord.Interaction):
        if not await salon_est_autorise("besoin_d_aide", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        class BesoinAideModal(discord.ui.Modal, title="Décris ton besoin d’aide"):
            description = discord.ui.TextInput(
                label="Décris ton problème ou besoin",
                style=discord.TextStyle.paragraph,
                placeholder="Ex : je suis bloqué sur une question, j’ai besoin d’un coup de main pour m’organiser...",
                required=True
            )

            async def on_submit(modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)

                try:
                    user = modal_interaction.user
                    guild = modal_interaction.guild
                    config = charger_config()
                    role_aide_id = config.get("role_aide")
                    role_aide = guild.get_role(int(role_aide_id)) if role_aide_id else None

                    # Créer un rôle temporaire pour le demandeur
                    temp_role = await get_or_create_role(guild, f"Aide-{user.name}")
                    await user.add_roles(temp_role)

                    # Créer la catégorie privée
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        temp_role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    if role_aide:
                        overwrites[role_aide] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                    category = await guild.create_category(f"aide-{user.name}".lower(), overwrites=overwrites)
                    await guild.create_text_channel("écris-ici", category=category)
                    await guild.create_voice_channel("parle-ici", category=category)

                    # Poster dans le salon public (là où la commande a été tapée)
                    embed = discord.Embed(
                        title="📣 Nouvelle demande d’aide",
                        description=self.description.value,
                        color=discord.Color.orange()
                    )
                    embed.set_footer(text=f"Demandée par {user.display_name}")

                    view = AideView(user, category, temp_role)
                    await interaction.channel.send(embed=embed, view=view)

                    # Ping du rôle d’aide dans le salon privé
                    if role_aide:
                        salon_text = discord.utils.get(category.channels, type=discord.ChannelType.text)
                        if salon_text:
                            await salon_text.send(
                                f"🔔 {role_aide.mention} – {user.mention} a besoin d’aide :\n{self.description.value}"
                            )

                    await modal_interaction.followup.send("✅ Demande envoyée et espace privé créé avec succès.", ephemeral=True)

                except Exception as e:
                    await modal_interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

        class AideView(discord.ui.View):
            def __init__(self, demandeur: discord.Member, category: discord.CategoryChannel, temp_role: discord.Role):
                super().__init__(timeout=None)
                self.demandeur = demandeur
                self.category = category
                self.temp_role = temp_role

            @discord.ui.button(label="J’ai aussi besoin d’aide", style=discord.ButtonStyle.primary)
            async def rejoindre(self, interaction: discord.Interaction, button: discord.ui.Button):
                if self.temp_role not in interaction.user.roles:
                    await interaction.user.add_roles(self.temp_role)
                    await interaction.response.send_message("✅ Tu as été ajouté à l’espace privé d’aide.", ephemeral=True)
                else:
                    await interaction.response.send_message("ℹ️ Tu fais déjà partie de l’espace d’aide.", ephemeral=True)

            @discord.ui.button(label="Supprimer", style=discord.ButtonStyle.danger)
            async def supprimer(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != self.demandeur:
                    return await interaction.response.send_message("❌ Seul le créateur peut supprimer cette demande.", ephemeral=True)
                try:
                    await self.category.delete()
                    await self.demandeur.remove_roles(self.temp_role)
                    await interaction.response.send_message("✅ Demande supprimée et espace privé fermé.", ephemeral=True)
                except Exception as e:
                    await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

        await interaction.response.send_modal(BesoinAideModal())

    # ───────────── /journal_burnout ─────────────
    @app_commands.command(name="journal_burnout", description="Signale un mal-être ou burn-out.")
    @app_commands.describe(message="Décris ce que tu ressens.")
    async def journal_burnout(self, interaction: discord.Interaction, message: str):
        if not await salon_est_autorise("journal_burnout", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            channel_id = get_redirection("burnout")
            if channel_id is None:
                return await interaction.followup.send("❌ Aucune redirection configurée pour burn-out.", ephemeral=True)
            channel = interaction.guild.get_channel(int(channel_id))
            if not channel:
                return await interaction.followup.send("❌ Salon introuvable.", ephemeral=True)

            embed = discord.Embed(
                title="🚨 Signalement Burn-Out",
                description=message,
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_footer(text=f"Par {interaction.user.display_name}")
            await channel.send(embed=embed)
            await interaction.followup.send("🆘 Message transmis à l’équipe. Courage à toi ❤️", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

    # ───────────── /auto_motivation ─────────────
    @app_commands.command(name="auto_motivation", description="Reçois un boost de motivation.")
    async def auto_motivation(self, interaction: discord.Interaction):
        if not await salon_est_autorise("auto_motivation", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
        citations = [
            "🔥 Chaque jour compte, ne lâche rien !",
            "🎯 Pense à ton objectif et dépasse tes limites.",
            "🌟 La discipline forge la réussite.",
            "💪 Fais ce que tu dois pour être fier de toi demain."
        ]
        await interaction.response.send_message(f"💬 {random.choice(citations)}", ephemeral=True)

    # ───────────── /challenge_semaine ─────────────
    @app_commands.command(name="challenge_semaine", description="Reçois un défi à appliquer cette semaine.")
    async def challenge_semaine(self, interaction: discord.Interaction):
        if not await salon_est_autorise("challenge_semaine", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
        challenges = [
            "🛌 Se coucher avant 23h chaque soir.",
            "📵 Une journée sans réseaux sociaux.",
            "📚 Revoir ses erreurs chaque soir.",
            "🤝 Aider un camarade en difficulté.",
            "🧘 Faire 10 minutes de méditation quotidienne."
        ]
        await interaction.response.send_message(f"📆 Challenge de la semaine : **{random.choice(challenges)}**", ephemeral=True)

    # ───────────── /creer_categorie_privee ─────────────
    @app_commands.command(name="creer_categorie_privee", description="Crée une catégorie privée accessible aux rôles spécifiés.")
    @app_commands.describe(
        nom_categorie="Nom de la catégorie",
        roles="Liste des IDs de rôles séparés par virgule"
    )
    async def creer_categorie_privee(self, interaction: discord.Interaction, nom_categorie: str, roles: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Vous devez être admin.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        allowed_roles = []
        try:
            for role_id in [r.strip() for r in roles.split(",")]:
                role = interaction.guild.get_role(int(role_id))
                if role:
                    allowed_roles.append(role)
                else:
                    return await interaction.followup.send(f"❌ Rôle introuvable : {role_id}", ephemeral=True)

            overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False)}
            for role in allowed_roles:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            category = await interaction.guild.create_category(nom_categorie, overwrites=overwrites)
            await interaction.followup.send(f"✅ Catégorie **{category.name}** créée avec succès.", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

async def setup_support_commands(bot):
    await bot.add_cog(SupportCommands(bot))
