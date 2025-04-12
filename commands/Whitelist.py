import discord
from discord import app_commands
from discord.ext import commands, tasks
import json, os, asyncio
from datetime import datetime, timedelta
from utils.utils import is_admin, charger_config, sauvegarder_config, log_erreur

DEMANDES_PATH = "data/demandes_whitelist.json"

class Whitelist(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.rappel_demande.start()

    # ====== Utilitaires JSON ======
    def charger_demandes(self):
        if not os.path.exists(DEMANDES_PATH):
            return []
        with open(DEMANDES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)

    def sauvegarder_demandes(self, data):
        os.makedirs("data", exist_ok=True)
        with open(DEMANDES_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def ajouter_demande(self, user_id, timestamp):
        demandes = self.charger_demandes()
        demandes.append({"user_id": user_id, "timestamp": timestamp})
        self.sauvegarder_demandes(demandes)

    def supprimer_demande(self, user_id):
        demandes = self.charger_demandes()
        demandes = [d for d in demandes if d["user_id"] != user_id]
        self.sauvegarder_demandes(demandes)

    # ====== Commande utilisateur ======
    @app_commands.command(name="demander_acces", description="Demande l'accès au serveur (réservé aux nouveaux membres)")
    async def demander_acces(self, interaction: discord.Interaction):
        try:
            config = charger_config()
            role_non_verifie = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            if role_non_verifie not in interaction.user.roles:
                return await interaction.response.send_message("❌ Vous avez déjà été validé.", ephemeral=True)

            self.ajouter_demande(interaction.user.id, datetime.utcnow().isoformat())

            embed = discord.Embed(
                title="Nouvelle demande d'accès",
                description=f"{interaction.user.mention} a demandé à rejoindre le serveur.",
                color=discord.Color.blurple()
            )
            embed.set_footer(text=f"ID utilisateur : {interaction.user.id}")

            view = ValidationButtons(self.bot, interaction.user.id)

            journal_channel = interaction.guild.get_channel(int(config.get("journal_validation_channel", 0)))
            if journal_channel:
                await journal_channel.send(embed=embed, view=view)

            await interaction.response.send_message("✅ Votre demande a été envoyée aux administrateurs. Merci de patienter !", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"demander_acces: {e}")
            await interaction.response.send_message("❌ Erreur lors de la demande.", ephemeral=True)

    # ====== Commandes admin ======
    @app_commands.command(name="definir_journal_validation", description="Définit le salon où les demandes seront journalisées.")
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        config = charger_config()
        config["journal_validation_channel"] = str(salon.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Salon de journal défini : {salon.mention}", ephemeral=True)

    @app_commands.command(name="definir_salon_rappel", description="Définit le salon où les rappels automatiques sont envoyés.")
    async def definir_salon_rappel(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        config = charger_config()
        config["salon_rappel_whitelist"] = str(salon.id)
        sauvegarder_config(config)
        await interaction.response.send_message(f"✅ Salon de rappel défini : {salon.mention}", ephemeral=True)

    @app_commands.command(name="definir_message_validation", description="Définit le message envoyé après validation.")
    async def definir_message_validation(self, interaction: discord.Interaction, message: str):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        config = charger_config()
        config["message_validation"] = message
        sauvegarder_config(config)
        await interaction.response.send_message("✅ Message de validation enregistré.", ephemeral=True)

    # ====== Tâche de rappel ======
    @tasks.loop(minutes=60)
    async def rappel_demande(self):
        try:
            config = charger_config()
            salon_id = config.get("salon_rappel_whitelist")
            if not salon_id:
                return
            salon = self.bot.get_channel(int(salon_id))
            if not salon:
                return

            demandes = self.charger_demandes()
            if not demandes:
                return

            for d in demandes:
                user = self.bot.get_user(int(d["user_id"]))
                if user:
                    await salon.send(f"⏰ Rappel : {user.mention} attend toujours une validation.")
        except Exception as e:
            print(f"Erreur dans rappel_demande: {e}")

# ====== Vue avec boutons pour accepter/refuser ======
class ValidationButtons(discord.ui.View):
    def __init__(self, bot, user_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = interaction.guild.get_member(self.user_id)
            if not user:
                return await interaction.response.send_message("Utilisateur introuvable.", ephemeral=True)

            role_non_verifie = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            role_membre = discord.utils.get(interaction.guild.roles, name="Membre")
            if role_non_verifie in user.roles:
                await user.remove_roles(role_non_verifie)
            if role_membre not in user.roles:
                await user.add_roles(role_membre)

            config = charger_config()
            message = config.get("message_validation", "Tu as été accepté ! Bienvenue sur le serveur !")
            try:
                await user.send(message)
            except:
                pass

            whitelist_cog = self.bot.get_cog("Whitelist")
            if whitelist_cog:
                whitelist_cog.supprimer_demande(user.id)

            await interaction.response.send_message("✅ Utilisateur accepté.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons accepter: {e}")
            await interaction.response.send_message("❌ Erreur lors de la validation.", ephemeral=True)

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            user = interaction.guild.get_member(self.user_id)
            if not user:
                return await interaction.response.send_message("Utilisateur introuvable.", ephemeral=True)

            try:
                await user.send("❌ Votre demande d'accès au serveur a été refusée. Contactez l'administration si besoin.")
            except:
                pass

            whitelist_cog = self.bot.get_cog("Whitelist")
            if whitelist_cog:
                whitelist_cog.supprimer_demande(user.id)

            await interaction.response.send_message("⛔ Utilisateur refusé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"ValidationButtons refuser: {e}")
            await interaction.response.send_message("❌ Erreur lors du refus.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Whitelist(bot))
