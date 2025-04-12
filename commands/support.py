import discord
from discord import app_commands
from discord.ext import commands
from utils.utils import salon_est_autorise, is_admin, get_or_create_role, get_redirection, charger_config
import datetime
import random

class SupportCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ───────────── /besoin_d_aide ─────────────
    @app_commands.command(name="besoin_d_aide", description="Demande d'aide avec création d'un espace privé.")
    async def besoin_d_aide(self, interaction: discord.Interaction):
        if not await salon_est_autorise("besoin_d_aide", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        class BesoinAideModal(discord.ui.Modal, title="Décris ton besoin d'aide"):
            sujet = discord.ui.TextInput(
                label="Sujet",
                placeholder="Ex: Difficultés en anatomie",
                required=True,
                max_length=100
            )
            description = discord.ui.TextInput(
                label="Détails",
                placeholder="Explique ton problème en détail",
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=400
            )

            async def on_submit(self, modal_interaction: discord.Interaction):
                await modal_interaction.response.defer(ephemeral=True)

                try:
                    user = modal_interaction.user
                    guild = modal_interaction.guild

                    # Rôle temporaire
                    role_temp = await get_or_create_role(guild, f"Aide-{user.name}")
                    await user.add_roles(role_temp)

                    # Rôle d’aide configuré
                    from utils.utils import charger_config
                    config = charger_config()
                    role_aide_id = config.get("role_aide")
                    role_aide = guild.get_role(int(role_aide_id)) if role_aide_id else None

                    # Overwrites
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        role_temp: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    if role_aide:
                        overwrites[role_aide] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

                    category = await guild.create_category(f"aide-{user.name}".lower(), overwrites=overwrites)
                    text_channel = await guild.create_text_channel("écris-ici", category=category)
                    await guild.create_voice_channel("parle-ici", category=category)

                    # Embed public
                    embed = discord.Embed(
                        title=f"🆘 Demande d'aide : {self.sujet.value}",
                        description=self.description.value,
                        color=discord.Color.orange(),
                        timestamp=datetime.datetime.utcnow()
                    )
                    embed.set_footer(text=f"Demandée par {user.display_name}")
                    view = AideView(user, category, role_temp)
                    await interaction.channel.send(embed=embed, view=view)

                    # Message dans le privé
                    if role_aide:
                        await text_channel.send(
                            f"🔔 {role_aide.mention}, une demande d’aide a été créée par {user.mention}.\n\n"
                            f"**Sujet :** {self.sujet.value}\n"
                            f"**Détails :** {self.description.value}"
                        )

                    await modal_interaction.followup.send("✅ Espace privé créé et demande envoyée.", ephemeral=True)

                except Exception as e:
                    await modal_interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

        await interaction.response.send_modal(BesoinAideModal(timeout=None))


# ───────────── Vue interactive avec boutons ─────────────
class AideView(discord.ui.View):
    def __init__(self, demandeur, category, temp_role):
        super().__init__(timeout=None)
        self.demandeur = demandeur
        self.category = category
        self.temp_role = temp_role

    @discord.ui.button(label="J’ai aussi ce problème", style=discord.ButtonStyle.primary)
    async def rejoindre_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.temp_role not in interaction.user.roles:
            await interaction.user.add_roles(self.temp_role)
            await interaction.response.send_message("✅ Vous avez rejoint l’espace d’aide.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ Vous êtes déjà dans cet espace.", ephemeral=True)

    @discord.ui.button(label="Supprimer la demande", style=discord.ButtonStyle.danger)
    async def supprimer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.demandeur:
            return await interaction.response.send_message("❌ Seul le demandeur peut supprimer la demande.", ephemeral=True)

        try:
            await self.category.delete()
            await self.demandeur.remove_roles(self.temp_role)
            await interaction.response.send_message("✅ La demande a été supprimée.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)

# ───────────── AUTRES COMMANDES ─────────────

    @app_commands.command(name="journal_burnout", description="Signale un mal-être ou burn-out.")
    @app_commands.describe(message="Décris ce que tu ressens.")
    async def journal_burnout(self, interaction: discord.Interaction, message: str):
        if not await salon_est_autorise("journal_burnout", interaction.channel_id, interaction.user):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        channel_id = get_redirection("burnout")
        if channel_id is None:
            return await interaction.followup.send("❌ Aucun salon de redirection configuré pour `burnout`.", ephemeral=True)
        salon = interaction.guild.get_channel(int(channel_id))
        if not salon:
            return await interaction.followup.send("❌ Salon de redirection introuvable.", ephemeral=True)

        embed = discord.Embed(
            title="🚨 Signalement Burn-Out",
            description=message,
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Par {interaction.user.display_name}")
        await salon.send(embed=embed)
        await interaction.followup.send("🆘 Ton message a été transmis à l’équipe.", ephemeral=True)

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

    @app_commands.command(name="creer_categorie_privee", description="Crée une catégorie privée pour des rôles.")
    @app_commands.describe(nom_categorie="Nom de la catégorie", roles="IDs des rôles autorisés (séparés par des virgules)")
    async def creer_categorie_privee(self, interaction: discord.Interaction, nom_categorie: str, roles: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            ids = [int(r.strip()) for r in roles.split(",")]
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False)
            }
            for rid in ids:
                role = interaction.guild.get_role(rid)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            category = await interaction.guild.create_category(nom_categorie, overwrites=overwrites)
            await interaction.followup.send(f"✅ Catégorie **{category.name}** créée avec succès.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

# ───────────── FIN DU COG ─────────────

async def setup_support_commands(bot):
    await bot.add_cog(SupportCommands(bot))
