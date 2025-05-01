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
    is_non_verified_user,
    role_autorise
)

# Chemin du fichier stockant les demandes (en attente)
DEMANDES_PATH = "data/demandes_whitelist.json"

def _charger_demandes():
    if not os.path.exists(DEMANDES_PATH):
        return []
    try:
        with open(DEMANDES_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _sauvegarder_demandes(data):
    os.makedirs("data", exist_ok=True)
    with open(DEMANDES_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

class ValidationButtons(discord.ui.View):
    def __init__(self, bot, user_id, nom, prenom):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.nom = nom
        self.prenom = prenom

    @discord.ui.button(label="✅ Accepter", style=discord.ButtonStyle.success)
    async def accepter(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            member = interaction.guild.get_member(self.user_id)
            if not member:
                return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)
            role_nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            role_membre = discord.utils.get(interaction.guild.roles, name="Membre")
            if role_nv and role_nv in member.roles:
                await member.remove_roles(role_nv)
            if role_membre and role_membre not in member.roles:
                await member.add_roles(role_membre)
            cfg = charger_config()
            msg_val = cfg.get("message_validation", "🎉 Bienvenue sur le serveur !")
            try:
                await member.send(msg_val)
            except:
                pass
            from utils.utils import charger_whitelist, sauvegarder_whitelist
            approved = await interaction.client.loop.run_in_executor(None, charger_whitelist)
            if not any(entry.get("user_id")==str(self.user_id) for entry in approved):
                approved.append({
                    "user_id": str(self.user_id),
                    "nom": self.nom,
                    "prenom": self.prenom,
                    "validated": datetime.utcnow().isoformat()
                })
                await interaction.client.loop.run_in_executor(None, sauvegarder_whitelist, approved)
            # retirer de demandes en attente
            cog = self.bot.get_cog("whitelist")
            if cog:
                await cog.supprimer_demande(self.user_id)
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("✅ Utilisateur accepté.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Accepter erreur: {e}")

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.danger)
    async def refuser(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            member = interaction.guild.get_member(self.user_id)
            if member:
                try:
                    await member.send("❌ Votre demande a été refusée. Contactez un modérateur si besoin.")
                except:
                    pass
            cog = self.bot.get_cog("whitelist")
            if cog:
                await cog.supprimer_demande(self.user_id)
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.followup.send("⛔ Utilisateur refusé.", ephemeral=True)
        except Exception as e:
            await log_erreur(self.bot, interaction.guild, f"Refuser erreur: {e}")

class Whitelist(commands.Cog, name="whitelist"):
    def __init__(self, bot):
        self.bot = bot
        self.rappel_demande.start()

    def cog_unload(self):
        self.rappel_demande.cancel()

    # gestion des demandes
    async def charger_demandes(self):
        return await self.bot.loop.run_in_executor(None, _charger_demandes)

    async def sauvegarder_demandes(self, data):
        await self.bot.loop.run_in_executor(None, lambda: _sauvegarder_demandes(data))

    async def ajouter_demande(self, user_id, timestamp, nom, prenom):
        demandes = await self.charger_demandes()
        for d in demandes:
            if d.get("user_id")==str(user_id):
                d.update({"timestamp": timestamp, "nom": nom, "prenom": prenom})
                break
        else:
            demandes.append({"user_id": str(user_id), "timestamp": timestamp, "nom": nom, "prenom": prenom})
        await self.sauvegarder_demandes(demandes)

    async def supprimer_demarche(self, user_id):
        demandes = await self.charger_demandes()
        nouvelles = [d for d in demandes if d.get("user_id")!=str(user_id)]
        await self.sauvegarder_demandes(nouvelles)

    async def supprimer_demande(self, user_id):
        await self.supprimer_demarche(user_id)

    # command admin pour config salon de validation
    @app_commands.command(
        name="definir_journal_validation",
        description="Définit le salon où sont envoyées les demandes."
    )
    @app_commands.default_permissions(administrator=True)
    async def definir_journal_validation(self, interaction: discord.Interaction, salon: discord.TextChannel):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
        cfg = charger_config()
        cfg["journal_validation_channel"] = str(salon.id)
        sauvegarder_config(cfg)
        await interaction.response.send_message(f"✅ Salon de validation défini : {salon.mention}", ephemeral=True)

    # command admin pour publier le message à réagir
    @app_commands.command(
        name="setup_whitelist_reaction",
        description="Publie le message de demande d'accès à réagir."
    )
    @app_commands.default_permissions(administrator=True)
    async def setup_whitelist_reaction(self,
            interaction: discord.Interaction,
            salon: discord.TextChannel,
            emoji: str = "✉️"
        ):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)

        embed = discord.Embed(
            title="Demande d'accès",
            description=f"Réagissez avec {emoji} pour demander l'accès au serveur.",
            color=discord.Color.blurple()
        )
        msg = await salon.send(embed=embed)
        try:
            await msg.add_reaction(emoji)
        except:
            pass

        cfg = charger_config()
        cfg["whitelist_reaction_channel_id"] = str(salon.id)
        cfg["whitelist_reaction_message_id"] = str(msg.id)
        cfg["whitelist_reaction_emoji"] = emoji
        sauvegarder_config(cfg)
        await interaction.response.send_message(
            f"✅ Message de demande publié en {salon.mention}.", ephemeral=True
        )

    # listener pour réactions
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        cfg = charger_config()
        mid = cfg.get("whitelist_reaction_message_id")
        chid = cfg.get("whitelist_reaction_channel_id")
        emoji = cfg.get("whitelist_reaction_emoji")
        if not (mid and chid and emoji):
            return
        if str(payload.message_id) != mid or str(payload.channel_id) != chid:
            return
        if str(payload.emoji) != emoji:
            return
        if payload.user_id == self.bot.user.id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        role_nv = discord.utils.get(guild.roles, name="Non vérifié")
        if not member or role_nv not in member.roles:
            return

        # supprime la réaction pour éviter multiples
        channel = self.bot.get_channel(payload.channel_id)
        try:
            await channel.remove_reaction(emoji, member)
        except:
            pass

        # démarrage du questionnaire en DM
        user = self.bot.get_user(payload.user_id)
        try:
            dm = await user.create_dm()
            await dm.send("Va dans tes messages privés, je te pose quelques questions…")
        except discord.Forbidden:
            return await channel.send(f"{member.mention}, active tes MP pour que je puisse te poser les questions.", delete_after=10)

        def check_msg(m):
            return m.author.id == payload.user_id and isinstance(m.channel, discord.DMChannel)

        try:
            await dm.send("Quel est ton **prénom** ?")
            resp_prenom = await self.bot.wait_for('message', timeout=60.0, check=check_msg)
            prenom = resp_prenom.content.strip()

            await dm.send("Quel est ton **nom** ?")
            resp_nom = await self.bot.wait_for('message', timeout=60.0, check=check_msg)
            nom = resp_nom.content.strip()

        except asyncio.TimeoutError:
            return await dm.send("⏱️ Temps écoulé. Recommence la réaction pour relancer la demande.", delete_after=30)

        # enregistrement de la demande
        await self.ajouter_demande(
            user_id=payload.user_id,
            timestamp=datetime.utcnow().isoformat(),
            nom=nom,
            prenom=prenom
        )

        # envoi de l'embed en validation
        embed = discord.Embed(
            title="📨 Nouvelle demande d'accès",
            description=(
                f"<@{payload.user_id}> a demandé à rejoindre le serveur.\n"
                f"**Nom** : {nom}\n"
                f"**Prénom** : {prenom}"
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text=f"ID utilisateur : {payload.user_id}")

        vid = cfg.get("journal_validation_channel")
        target = guild.get_channel(int(vid)) if vid else None
        if target:
            view = ValidationButtons(self.bot, payload.user_id, nom, prenom)
            await target.send(embed=embed, view=view)
            await dm.send("✅ Merci, ta demande a bien été transmise aux modérateurs.")
        else:
            await dm.send("⚠️ Ta demande est enregistrée, mais aucun salon de validation n'est configuré. Contacte un modérateur.")

    # rappel périodique
    @tasks.loop(minutes=60)
    async def rappel_demande(self):
        try:
            cfg = charger_config()
            rid = cfg.get("salon_rappel_whitelist")
            if not rid:
                return
            salon = self.bot.get_channel(int(rid))
            if not salon:
                return
            demandes = await self.charger_demandes()
            for d in demandes:
                user = self.bot.get_user(int(d["user_id"]))
                if user:
                    nom = d.get("nom", "Inconnu")
                    prenom = d.get("prenom", "Inconnu")
                    await salon.send(f"⏰ Rappel : {user.mention} ({nom} {prenom}) attend toujours une validation.")
        except Exception as e:
            await log_erreur(self.bot, None, f"rappel_demande : {e}")

    # permissions & recherche & retrait inchangées...
    @app_commands.command(
        name="rechercher_whitelist",
        description="Recherche un utilisateur dans la whitelist par nom ou prénom."
    )
    async def rechercher_whitelist(self, interaction: discord.Interaction, query: str):
        if not (await is_admin(interaction.user) or role_autorise(interaction, "rechercher_whitelist")):
            return await interaction.response.send_message("❌ Pas la permission.", ephemeral=True)
        from utils.utils import charger_whitelist
        approved = await self.bot.loop.run_in_executor(None, charger_whitelist)
        matches = [e for e in approved if query.lower() in e.get("nom","").lower() or query.lower() in e.get("prenom","").lower()]
        if not matches:
            return await interaction.response.send_message(f"❌ Aucun résultat pour '{query}'.", ephemeral=True)
        txt = "\n".join(f"ID:{m['user_id']} • {m['prenom']} {m['nom']} ({m.get('validated','?')})" for m in matches)
        await interaction.response.send_message(embed=discord.Embed(title="Résultats", description=txt, color=discord.Color.green()), ephemeral=True)

    @app_commands.command(
        name="retirer_whitelist",
        description="Retire un utilisateur de la whitelist et réinitialise son statut."
    )
    @app_commands.default_permissions(administrator=True)
    async def retirer_whitelist(self, interaction: discord.Interaction, utilisateur: discord.Member):
        if not await is_admin(interaction.user):
            return await interaction.response.send_message("❌ Réservé aux admins.", ephemeral=True)
        from utils.utils import charger_whitelist, sauvegarder_whitelist
        approved = await self.bot.loop.run_in_executor(None, charger_whitelist)
        entry = next((e for e in approved if e.get("user_id")==str(utilisateur.id)), None)
        if entry:
            approved.remove(entry)
            await self.bot.loop.run_in_executor(None, sauvegarder_whitelist, approved)
            r_nv = discord.utils.get(interaction.guild.roles, name="Non vérifié")
            r_m = discord.utils.get(interaction.guild.roles, name="Membre")
            if r_m in utilisateur.roles:
                await utilisateur.remove_roles(r_m)
            if r_nv not in utilisateur.roles:
                await utilisateur.add_roles(r_nv)
            await interaction.response.send_message(f"✅ {utilisateur.mention} retiré de la whitelist.", ephemeral=True)
        else:
            await interaction.response.send_message("ℹ️ Utilisateur non dans la whitelist.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Whitelist(bot))
