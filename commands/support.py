import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import random
from utils.utils import charger_config, sauvegarder_config, log_erreur, is_verified_user, is_admin

# Vérification pour les commandes support
async def check_verified(interaction: discord.Interaction) -> bool:
    if await is_verified_user(interaction.user):
        return True
    raise app_commands.CheckFailure("Commande réservée aux membres vérifiés.")

# Modal pour le journal burnout (déjà existant)
class JournalBurnoutModal(discord.ui.Modal, title="Journal Burn-Out"):
    message = discord.ui.TextInput(
        label="Décris ton état (anonymement)",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: Je suis épuisé(e), démotivé(e), etc...",
        required=True
    )
    emoji = discord.ui.TextInput(
        label="Emoji d'état (optionnel)",
        style=discord.TextStyle.short,
        placeholder="Ex: 😞, 😴, etc.",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            config = charger_config()
            burnout_channel_id = config.get("journal_burnout_channel")
            if not burnout_channel_id:
                await interaction.response.send_message("❌ Le salon pour le journal burnout n'est pas configuré.", ephemeral=True)
                return
            
            channel = interaction.guild.get_channel(int(burnout_channel_id))
            if not channel:
                await interaction.response.send_message("❌ Le salon pour le journal burnout est introuvable.", ephemeral=True)
                return

            emoji_used = self.emoji.value.strip() if self.emoji.value.strip() else random.choice(["😞", "😔", "😢", "😴", "😓", "💤"])

            embed = discord.Embed(
                title="🚨 Signalement de Burn-Out",
                description=self.message.value,
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.add_field(name="État", value=emoji_used, inline=True)
            embed.set_footer(text="Signalé anonymement")
            
            await channel.send(embed=embed)
            await interaction.response.send_message("✅ Ton signalement a été envoyé. Prends soin de toi.", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"JournalBurnoutModal on_submit: {e}")
            await interaction.response.send_message("❌ Une erreur est survenue lors de l'envoi de ton signalement.", ephemeral=True)

# Modal pour la commande /besoin_d_en_parler
class BesoinParlerModal(discord.ui.Modal, title="Besoin d'en parler"):
    niveau_stress = discord.ui.TextInput(
        label="Niveau de stress (1 à 5)",
        placeholder="Ex: 3",
        required=True
    )
    besoin = discord.ui.TextInput(
        label="Quel est ton besoin ?",
        placeholder="Ex: J'ai besoin d'en parler, de conseils, etc.",
        required=True
    )
    message = discord.ui.TextInput(
        label="Décris brièvement ce que tu ressens",
        style=discord.TextStyle.paragraph,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            config = charger_config()
            salon_id = config.get("salon_besoin_d_en_parler")
            if not salon_id:
                await interaction.response.send_message("❌ Le salon pour 'besoin d'en parler' n'est pas configuré.", ephemeral=True)
                return
            channel = interaction.guild.get_channel(int(salon_id))
            if not channel:
                await interaction.response.send_message("❌ Le salon pour 'besoin d'en parler' est introuvable.", ephemeral=True)
                return

            role_id = config.get("role_besoin_d_en_parler")
            role_ping = None
            if role_id:
                role_ping = interaction.guild.get_role(int(role_id))
            
            embed = discord.Embed(
                title="Nouvelle demande de 'Besoin d'en parler'",
                color=discord.Color.purple(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Niveau de stress", value=self.niveau_stress.value, inline=True)
            embed.add_field(name="Besoin", value=self.besoin.value, inline=False)
            embed.add_field(name="Message", value=self.message.value, inline=False)
            embed.set_footer(text=f"Demande envoyée par {interaction.user.display_name}", 
                             icon_url=interaction.user.avatar.url if interaction.user.avatar else None)
            
            content = f"{role_ping.mention}" if role_ping else None
            
            # Ajout de la vue avec le bouton "Créer un salon privé"
            view = CreationSalonPriveView(requester=interaction.user, demande_title=self.besoin.value)
            
            await channel.send(content=content, embed=embed, view=view)
            await interaction.response.send_message("✅ Ton besoin a été transmis aux intervenants. Prends soin de toi.", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"BesoinParlerModal on_submit: {e}")
            await interaction.response.send_message("❌ Une erreur est survenue lors de l'envoi de ta demande.", ephemeral=True)

# Vue pour créer un salon privé pour traiter la demande
class CreationSalonPriveView(discord.ui.View):
    def __init__(self, requester: discord.Member, demande_title: str):
        super().__init__(timeout=None)
        self.requester = requester
        self.demande_title = demande_title

    @discord.ui.button(label="Créer un salon privé", style=discord.ButtonStyle.primary)
    async def creer_salon_prive(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Vérifier que la personne qui clique possède le rôle d'intervenant
        config = charger_config()
        role_id = config.get("role_besoin_d_en_parler")
        if not role_id:
            return await interaction.response.send_message("❌ Le rôle intervenant n'est pas configuré.", ephemeral=True)
        role_intervenant = interaction.guild.get_role(int(role_id))
        if role_intervenant not in interaction.user.roles:
            return await interaction.response.send_message("❌ Vous n'êtes pas autorisé à créer un salon privé pour cette demande.", ephemeral=True)
        
        try:
            # Création du nom de la catégorie : "NomDemandeur - Besoin: <titre>"
            category_name = f"{self.requester.display_name} - {self.demande_title}"
            
            # Définition des permissions : accès uniquement pour le demandeur et pour le rôle intervenant
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                self.requester: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                role_intervenant: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            
            # Création de la catégorie privée
            category = await interaction.guild.create_category(category_name, overwrites=overwrites)
            
            # Création des salons texte et vocal dans la catégorie
            text_channel = await interaction.guild.create_text_channel("discussion", category=category)
            voice_channel = await interaction.guild.create_voice_channel("support-voice", category=category)
            
            # Dans le salon texte, envoi d'un message pinguant le demandeur pour clarifier son besoin
            clarif_message = f"{self.requester.mention}, Ce salon a été créé spécialement pour toi, seul la personne qui viendra t'aider pourra tout supprimer afin que tu ne puisses pas faire marche arrière et soit vraiment aidé ! N'hésite pas à détailler un peu plus ton besoin si nécessaire !"
            # Ajout de la vue pour supprimer le salon (bouton "Problème réglé")
            suppression_view = SuppressionSalonView(category=category, role_intervenant=role_intervenant)
            await text_channel.send(clarif_message, view=suppression_view)
            
            await interaction.response.send_message("✅ Salon privé créé avec succès.", ephemeral=True)
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"Erreur dans création de salon privé: {e}")
            await interaction.response.send_message("❌ Une erreur est survenue lors de la création du salon privé.", ephemeral=True)

# Vue pour supprimer la catégorie privée avec tous ses salons (bouton "Problème réglé")
class SuppressionSalonView(discord.ui.View):
    def __init__(self, category: discord.CategoryChannel, role_intervenant: discord.Role):
        super().__init__(timeout=None)
        self.category = category
        self.role_intervenant = role_intervenant

    @discord.ui.button(label="Problème réglé", style=discord.ButtonStyle.success)
    async def supprimer_salon(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Seul un intervenant (possédant le rôle défini) peut cliquer
        if self.role_intervenant not in interaction.user.roles:
            return await interaction.response.send_message("❌ Vous n'êtes pas autorisé à fermer cet espace.", ephemeral=True)
        try:
            await interaction.response.defer(ephemeral=True)
            # Supprimer chaque salon de la catégorie
            for channel in list(self.category.channels):
                try:
                    await channel.delete()
                except Exception as e:
                    await log_erreur(interaction.client, interaction.guild, f"Erreur lors de la suppression du salon {channel.name}: {e}")
            # Supprimer la catégorie elle-même
            await self.category.delete()
            await interaction.followup.send("✅ L'espace privé a été fermé avec succès.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors de la fermeture de l'espace: {e}", ephemeral=True)

# Cog regroupant les commandes support, incluant journal burnout et la nouvelle commande besoin d'en parler
class SupportCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "❌ Vous n'avez pas accès aux commandes support. Si vous rencontrez un problème, contactez le staff.",
                ephemeral=True
            )
        else:
            await log_erreur(self.bot, interaction.guild, f"SupportCommands error: {error}")
            raise error

    @app_commands.command(name="journal_burnout", description="Signale anonymement une baisse de moral, une fatigue mentale ou un burn-out.")
    @app_commands.check(check_verified)
    async def journal_burnout(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(JournalBurnoutModal())
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"journal_burnout: {e}")
            await interaction.response.send_message("❌ Une erreur est survenue lors de l'ouverture du formulaire.", ephemeral=True)

    @app_commands.command(name="besoin_d_en_parler", description="Permet de signaler un besoin de parler ou de soutien de manière confidentielle.")
    @app_commands.check(check_verified)
    async def besoin_d_en_parler(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(BesoinParlerModal())
        except Exception as e:
            await log_erreur(interaction.client, interaction.guild, f"besoin_d_en_parler: {e}")
            await interaction.response.send_message("❌ Une erreur est survenue lors de l'ouverture du formulaire.", ephemeral=True)

    # Commande admin pour définir le salon où seront envoyées les demandes de "besoin d'en parler"
    @app_commands.command(name="definir_salon_besoin", description="Définit le salon où seront envoyées les demandes de 'besoin d'en parler'.")
    @app_commands.default_permissions(administrator=True)
    async def definir_salon_besoin(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["salon_besoin_d_en_parler"] = str(salon.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Salon pour 'besoin d'en parler' défini : {salon.mention}", ephemeral=True)

    # Commande admin pour définir le rôle à ping dans une demande de "besoin d'en parler"
    @app_commands.command(name="definir_role_besoin", description="Définit le rôle à pinger lors d'une demande de 'besoin d'en parler'.")
    @app_commands.default_permissions(administrator=True)
    async def definir_role_besoin(self, interaction: discord.Interaction, role: discord.Role):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        config = charger_config()
        config["role_besoin_d_en_parler"] = str(role.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Rôle pour 'besoin d'en parler' défini : {role.mention}", ephemeral=True)

async def setup_support_commands(bot: commands.Bot):
    await bot.add_cog(SupportCommands(bot))
