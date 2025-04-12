import discord
from discord import app_commands
from discord.ext import commands
import random
import datetime
from utils.utils import salon_est_autorise, is_admin, get_or_create_role, get_redirection

class SupportCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ───────────── /besoin_d_aide ─────────────
    @app_commands.command(name="besoin_d_aide", description="Crée un espace privé pour poser tes questions.")
    async def besoin_d_aide(self, interaction: discord.Interaction):
        if not salon_est_autorise("besoin_d_aide", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
        guild = interaction.guild
        # Crée un rôle unique pour l'utilisateur
        role_name = f"Aide-{interaction.user.name}"
        role = await get_or_create_role(guild, role_name)
        # Configuration d'overwrites pour restreindre l'accès
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            role: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        category_name = f"aide-{interaction.user.name}".lower()
        category = await guild.create_category(category_name, overwrites=overwrites)
        await guild.create_text_channel("écris-ici", category=category)
        await guild.create_voice_channel("parle-ici", category=category)
        # Assigne le rôle à l'utilisateur
        await interaction.user.add_roles(role)
        await interaction.response.send_message(
            f"✅ Espace privé créé : **{category.name}**.\nTu peux échanger en toute confidentialité.",
            ephemeral=True
        )

    # ───────────── /journal_burnout ─────────────
    @app_commands.command(name="journal_burnout", description="Signale un mal-être ou burn-out.")
    @app_commands.describe(message="Décris ce que tu ressens.")
    async def journal_burnout(self, interaction: discord.Interaction, message: str):
        if not salon_est_autorise("journal_burnout", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
        # Cherche le salon de redirection configuré pour 'burnout'
        channel_id = get_redirection("burnout")
        if channel_id is None:
            return await interaction.response.send_message(
                "❌ Le salon de redirection pour les signalements de burn-out n'est pas configuré. Demande à un admin avec `/definir_redirection`.",
                ephemeral=True
            )
        channel = interaction.guild.get_channel(int(channel_id))
        if channel is None:
            return await interaction.response.send_message(
                "❌ Le salon configuré n'existe pas.",
                ephemeral=True
            )
        embed = discord.Embed(
            title="🚨 Signalement Burn-Out",
            description=message,
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        embed.set_footer(text=f"Par {interaction.user.display_name}")
        await channel.send(embed=embed)
        await interaction.response.send_message(
            "🆘 Ton message a été transmis à l’équipe. Courage à toi ❤️",
            ephemeral=True
        )

    # ───────────── /auto_motivation ─────────────
    @app_commands.command(name="auto_motivation", description="Reçois un boost de motivation.")
    async def auto_motivation(self, interaction: discord.Interaction):
        if not salon_est_autorise("auto_motivation", interaction.channel_id):
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
        if not salon_est_autorise("challenge_semaine", interaction.channel_id):
            return await interaction.response.send_message("❌ Commande non autorisée dans ce salon.", ephemeral=True)
        challenges = [
            "🛌 Se coucher avant 23h chaque soir.",
            "📵 Une journée sans réseaux sociaux.",
            "📚 Revoir ses erreurs en 5 minutes chaque soir.",
            "🤝 Aider un camarade en difficulté.",
            "🧘 Faire 10 minutes de méditation quotidienne."
        ]
        await interaction.response.send_message(f"📆 Challenge de la semaine : **{random.choice(challenges)}**", ephemeral=True)

        # ───────────── /creer_categorie_privee ─────────────
    @app_commands.command(
        name="creer_categorie_privee",
        description="Crée une catégorie privée accessible uniquement aux rôles spécifiés."
    )
    @app_commands.describe(
        nom_categorie="Nom de la nouvelle catégorie privée",
        roles="Liste séparée par des virgules des ID des rôles autorisés (ex: 123456789012345678, 987654321098765432)"
    )
    async def creer_categorie_privee(self, interaction: discord.Interaction, nom_categorie: str, roles: str):
        # Vérification que l'utilisateur est admin
        if not await is_admin(interaction.user):
            return await interaction.response.send_message(
                "❌ Vous devez être administrateur pour utiliser cette commande.",
                ephemeral=True
            )

        allowed_roles = []
        # On attend que l'administrateur fournisse les ID des rôles séparés par des virgules.
        role_ids = [r.strip() for r in roles.split(",")]
        for role_id in role_ids:
            try:
                role_id_int = int(role_id)
                role = interaction.guild.get_role(role_id_int)
                if role is None:
                    return await interaction.response.send_message(
                        f"❌ Aucun rôle trouvé pour l'ID {role_id}. Veuillez vérifier cet ID.",
                        ephemeral=True
                    )
                allowed_roles.append(role)
            except ValueError:
                return await interaction.response.send_message(
                    f"❌ L'ID '{role_id}' n'est pas valide (doit être numérique).",
                    ephemeral=True
                )

        # Définir les permissions (overwrites) pour la nouvelle catégorie :
        # - Refuser l'accès à @everyone
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False)
        }
        # - Accorder l'accès aux rôles spécifiés
        for role in allowed_roles:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Tenter de créer la catégorie privée avec ces overwrites
        try:
            category = await interaction.guild.create_category(nom_categorie, overwrites=overwrites)
            await interaction.response.send_message(
                f"✅ La catégorie privée **{category.name}** a été créée et est accessible aux rôles spécifiés.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Une erreur est survenue lors de la création de la catégorie : {e}",
                ephemeral=True
            )


async def setup_support_commands(bot):
    await bot.add_cog(SupportCommands(bot))
