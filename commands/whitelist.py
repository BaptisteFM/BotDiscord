import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime
from utils.utils import (
    is_admin,
    charger_config,
    sauvegarder_config,
    log_erreur,
    role_autorise,
    charger_whitelist,
    sauvegarder_whitelist
)

# Paths pour stockage JSON
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DEMANDES_PATH = os.path.join(DATA_DIR, 'demandes_whitelist.json')
# Verrou pour opérations fichier
file_lock = asyncio.Lock()

class ValidationButtons(discord.ui.View):
    def __init__(self, cog, user_id: int, nom: str, prenom: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.nom = nom
        self.prenom = prenom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            member = guild.get_member(self.user_id)
            if not member:
                return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)

            # Retirer role Non vérifié, ajouter Membre
            role_nv = discord.utils.get(guild.roles, name="Non vérifié")
            role_membre = discord.utils.get(guild.roles, name="Membre")
            if role_nv and role_nv in member.roles:
                await member.remove_roles(role_nv)
            if role_membre and role_membre not in member.roles:
                await member.add_roles(role_membre)

            # Enregistrer dans whitelist
            whitelist = await self.cog._read_json('whitelist.json')
            if not any(u['user_id']==str(self.user_id) for u in whitelist):
                whitelist.append({
                    'user_id': str(self.user_id),
                    'nom': self.nom,
                    'prenom': self.prenom,
                    'validated': datetime.utcnow().isoformat()
                })
                await self.cog._write_json('whitelist.json', whitelist)

            # Supprimer demande en attente
            await self.cog._remove_demande(self.user_id)
            # Supprimer message de validation
            try: await interaction.message.delete()
            except: pass

            # Notifier
            await interaction.followup.send("✅ Utilisateur accepté.", ephemeral=True)

            # Envoyer message de bienvenue
            cfg = charger_config()
            msg = cfg.get('message_validation', '🎉 Bienvenue !')
            try: await member.send(msg)
            except: pass

        except Exception as e:
            await log_erreur(self.cog.bot, interaction.guild, f"Erreur accepter: {e}")

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            # Notifier refus
            guild = interaction.guild
            member = guild.get_member(self.user_id)
            if member:
                try: await member.send("Votre demande a été refusée.")
                except: pass

            await self.cog._remove_demande(self.user_id)
            try: await interaction.message.delete()
            except: pass
            await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.cog.bot, interaction.guild, f"Erreur refuser: {e}")

class Whitelist(commands.Cog):
    """Cog de gestion de whitelist et demandes d'accès."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        os.makedirs(DATA_DIR, exist_ok=True)
        # Tâche de rappel
        self.rappel_demande.start()

    def cog_unload(self):
        self.rappel_demande.cancel()

    async def _read_json(self, filename: str) -> list:
        path = os.path.join(DATA_DIR, filename)
        async with file_lock:
            if not os.path.exists(path):
                return []
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return []

    async def _write_json(self, filename: str, data: list):
        path = os.path.join(DATA_DIR, filename)
        async with file_lock:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)

    async def _add_demande(self, user_id: int, nom: str, prenom: str):
        demandes = await self._read_json('demandes_whitelist.json')
        entry = next((d for d in demandes if d['user_id']==str(user_id)), None)
        if entry:
            entry.update({'timestamp': datetime.utcnow().isoformat(), 'nom': nom, 'prenom': prenom})
        else:
            demandes.append({'user_id': str(user_id), 'timestamp': datetime.utcnow().isoformat(), 'nom': nom, 'prenom': prenom})
        await self._write_json('demandes_whitelist.json', demandes)

    async def _remove_demande(self, user_id: int):
        demandes = await self._read_json('demandes_whitelist.json')
        demandes = [d for d in demandes if d['user_id'] != str(user_id)]
        await self._write_json('demandes_whitelist.json', demandes)

    # Commandes de configuration
    @app_commands.command(name="definir_journal_validation",
                          description="Définit le salon pour les demandes de validation.")
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Accès réservé aux admins.", ephemeral=True)
        cfg = charger_config()
        cfg['journal_validation_channel'] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de validation: {salon.mention}", ephemeral=True)

    @app_commands.command(name="setup_whitelist_reaction",
                          description="Publie le message de demande à réagir.")
    @app_commands.default_permissions(administrator=True)
    async def setup_whitelist_reaction(self,
                                       interaction: discord.Interaction,
                                       salon: discord.TextChannel,
                                       emoji: str = "✉️"):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Accès réservé aux admins.", ephemeral=True)
        embed = discord.Embed(
            title="Demande d'accès",
            description=f"Réagissez avec {emoji} pour accéder.",
            color=discord.Color.blurple()
        )
        msg = await salon.send(embed=embed)
        try: await msg.add_reaction(emoji)
        except: pass
        cfg = charger_config()
        cfg['whitelist_reaction_channel_id'] = str(salon.id)
        cfg['whitelist_reaction_message_id'] = str(msg.id)
        cfg['whitelist_reaction_emoji'] = emoji
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Message publié dans {salon.mention}.", ephemeral=True)

    # Listener réactions
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        cfg = charger_config()
        if (str(payload.message_id) != cfg.get('whitelist_reaction_message_id')
            or str(payload.channel_id) != cfg.get('whitelist_reaction_channel_id')
            or str(payload.emoji) != cfg.get('whitelist_reaction_emoji')
            or payload.user_id == self.bot.user.id):
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role_nv = discord.utils.get(guild.roles, name="Non vérifié")
        if not member or role_nv not in member.roles:
            return

        # Supprimer réaction
        channel = self.bot.get_channel(payload.channel_id)
        try: await channel.remove_reaction(payload.emoji, member)
        except: pass

        user = self.bot.get_user(payload.user_id)
        try:
            dm = await user.create_dm()
            await dm.send("Je vous pose quelques questions en MP…")
        except discord.Forbidden:
            return await channel.send(f"{member.mention}, active tes MP.", delete_after=10)

        def check(m): return m.author.id==payload.user_id and isinstance(m.channel, discord.DMChannel)
        try:
            await dm.send("Quel est ton **prénom** ?")
            resp1 = await self.bot.wait_for('message', timeout=60, check=check)
            prenom = resp1.content.strip()
            await dm.send("Quel est ton **nom** ?")
            resp2 = await self.bot.wait_for('message', timeout=60, check=check)
            nom = resp2.content.strip()
        except asyncio.TimeoutError:
            return await dm.send("⏱️ Temps écoulé, réagis de nouveau.")

        await self._add_demande(payload.user_id, nom, prenom)

        embed = discord.Embed(
            title="📨 Nouvelle demande",
            description=f"<@{payload.user_id}>\n**Prenom**: {prenom}\n**Nom**: {nom}",
            color=discord.Color.blurple()
        )
        footer = f"ID: {payload.user_id}"
        embed.set_footer(text=footer)
        target = guild.get_channel(int(cfg.get('journal_validation_channel', 0)))
        if target:
            view = ValidationButtons(self, payload.user_id, nom, prenom)
            await target.send(embed=embed, view=view)
            await dm.send("✅ Demande envoyée aux modérateurs.")
        else:
            await dm.send("⚠️ Salon de validation non configuré.")

    # Rappel périodique des demandes en attente
    @tasks.loop(hours=1)
    async def rappel_demande(self):
        try:
            cfg = charger_config()
            rid = cfg.get('salon_rappel_whitelist')
            if not rid:
                return
            channel = self.bot.get_channel(int(rid))
            demandes = await self._read_json('demandes_whitelist.json')
            for d in demandes:
                user = self.bot.get_user(int(d['user_id']))
                if user:
                    await channel.send(f"⏰ Rappel: {user.mention} attend validation.")
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande: {e}")

    # Commandes admin pour gérer whitelist
    @app_commands.command(name="rechercher_whitelist", description="Recherche dans la whitelist.")
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, "rechercher_whitelist")):
            return await interaction.response.send_message("❌ Pas la permission.", ephemeral=True)
        approved = await charger_whitelist()
        results = [u for u in approved if query.lower() in u.get('nom','').lower() or query.lower() in u.get('prenom','').lower()]
        if not results:
            return await interaction.response.send_message(f"❌ Aucun résultat pour '{query}'.", ephemeral=True)
        desc = '\n'.join(f"• {u['prenom']} {u['nom']} (ID:{u['user_id']})" for u in results)
        embed = discord.Embed(title="Résultats de recherche", description=desc, color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="retirer_whitelist", description="Retire un membre de la whitelist.")
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Accès réservé aux admins.", ephemeral=True)
        approved = await charger_whitelist()
        entry = next((u for u in approved if u.get('user_id')==str(utilisateur.id)), None)
        if not entry:
            return await interaction.response.send_message("ℹ️ Utilisateur non whitelisté.", ephemeral=True)
        approved.remove(entry)
        await sauvegarder_whitelist(approved)
        # Réinitialiser rôles
        r_nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
        r_m = discord.utils.get(interaction.guild.roles, name="Membre")
        if r_m and r_m in utilisateur.roles:
            await utilisateur.remove_roles(r_m)
        if r_nv and r_nv not in utilisateur.roles:
            await utilisateur.add_roles(r_nv)
        await interaction.response.send_message(f"✅ {utilisateur.mention} retiré.", ephemeral=True)

    @app_commands.command(name="lister_whitelist", description="Affiche la liste des membres whitelistés.")
    @app_commands.default_permissions(administrator=True)
    async def lister_whitelist(self, interaction: discord.Interaction):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Accès réservé aux admins.", ephemeral=True)
        approved = await charger_whitelist()
        count = len(approved)
        desc = '\n'.join(f"• {u['prenom']} {u['nom']} (ID:{u['user_id']})" for u in approved)
        embed = discord.Embed(title=f"Whitelist ({count})", description=desc or "Aucun membre.", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Whitelist(bot))
