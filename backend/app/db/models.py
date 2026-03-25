from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

UserRole = Enum("admin", "organizer", "cantina", "secretaria", name="user_role")

SportSlug = Enum(
    "futsal",
    "volleyball",
    "basketball",
    "running",
    "domino",
    "dama",
    "xadrez",
    "tenis_mesa",
    name="sport_slug",
)

ChampionshipFormat = Enum(
    "round_robin",
    "elimination",
    "hybrid",
    name="championship_format",
)

ChampionshipStatus = Enum(
    "draft",
    "active",
    "finished",
    name="championship_status",
)

GameStatus = Enum(
    "scheduled",
    "live",
    "finished",
    name="game_status",
)

GameEventType = Enum(
    "goal",
    "yellow_card",
    "red_card",
    "point",
    "foul",
    "point_1",
    "point_2",
    "free_throw",
    name="game_event_type",
)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id           = Column(Integer, primary_key=True)
    email        = Column(String(200), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name         = Column(String(100), nullable=False)
    role         = Column(UserRole, nullable=False, default="organizer")
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # relationships
    teams_created        = relationship("Team",         back_populates="creator",     foreign_keys="Team.created_by")
    championships_created = relationship("Championship", back_populates="creator",     foreign_keys="Championship.created_by")


# ---------------------------------------------------------------------------
# Sport
# ---------------------------------------------------------------------------

class Sport(Base):
    __tablename__ = "sports"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(100), unique=True, nullable=False)
    slug         = Column(SportSlug, unique=True, nullable=False)
    rules_config = Column(JSON, nullable=False, default=dict,
                          comment="Configuração de regras específicas da modalidade (ex: pontuação, sets, tempos)")

    # relationships
    teams         = relationship("Team",         back_populates="sport")
    championships = relationship("Championship", back_populates="sport")
    team_links    = relationship("TeamSport",    back_populates="sport")


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------

class Team(Base):
    __tablename__ = "teams"

    id         = Column(Integer, primary_key=True)
    name       = Column(String(100), nullable=False)
    logo_url   = Column(String(500))
    sport_id   = Column(Integer, ForeignKey("sports.id", ondelete="RESTRICT"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id",  ondelete="SET NULL"),  nullable=True,  index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # relationships
    sport    = relationship("Sport", back_populates="teams")
    creator  = relationship("User",  back_populates="teams_created", foreign_keys=[created_by])
    athletes = relationship("Athlete", back_populates="team", cascade="save-update, merge")

    championship_links = relationship("ChampionshipTeam", back_populates="team")
    sport_links        = relationship("TeamSport", back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_teams_sport_id", "sport_id"),
        Index("ix_teams_created_by", "created_by"),
    )

    @property
    def sports(self) -> list:
        """Todas as modalidades da equipe (via team_sports N:N)."""
        return [link.sport for link in self.sport_links if link.sport]


# ---------------------------------------------------------------------------
# TeamSport (N:N entre Team e Sport)
# ---------------------------------------------------------------------------

class TeamSport(Base):
    __tablename__ = "team_sports"

    id       = Column(Integer, primary_key=True)
    team_id  = Column(Integer, ForeignKey("teams.id",  ondelete="CASCADE"), nullable=False, index=True)
    sport_id = Column(Integer, ForeignKey("sports.id", ondelete="CASCADE"), nullable=False, index=True)

    team  = relationship("Team",  back_populates="sport_links")
    sport = relationship("Sport", back_populates="team_links")

    __table_args__ = (
        Index("uq_team_sport", "team_id", "sport_id", unique=True),
    )


# ---------------------------------------------------------------------------
# Athlete
# ---------------------------------------------------------------------------

class AthleteTeam(Base):
    """Relação N:N entre atleta e equipe, com restrição de 1 equipe por modalidade."""
    __tablename__ = "athlete_teams"

    id         = Column(Integer, primary_key=True)
    athlete_id = Column(Integer, ForeignKey("athletes.id", ondelete="CASCADE"), nullable=False)
    team_id    = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    sport_id   = Column(Integer, ForeignKey("sports.id", ondelete="CASCADE"), nullable=False)

    athlete = relationship("Athlete", back_populates="athlete_teams")
    team    = relationship("Team")
    sport   = relationship("Sport")

    __table_args__ = (
        Index("uq_athlete_sport", "athlete_id", "sport_id", unique=True),
        Index("uq_athlete_team_link", "athlete_id", "team_id", unique=True),
    )


class Athlete(Base):
    __tablename__ = "athletes"

    id       = Column(Integer, primary_key=True)
    name     = Column(String(100), nullable=False)
    number   = Column(Integer, comment="Número da camisa")
    position = Column(String(50),  comment="Posição ou função na equipe")
    team_id  = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True)
    photo_url = Column(String(500))
    active   = Column(Boolean, nullable=False, default=True)

    # relationships
    team         = relationship("Team",        back_populates="athletes")
    game_events  = relationship("GameEvent",   back_populates="athlete")
    suspensions  = relationship("Suspension",  back_populates="athlete")
    athlete_teams = relationship("AthleteTeam", back_populates="athlete", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_athletes_team_id", "team_id"),
    )


# ---------------------------------------------------------------------------
# Championship
# ---------------------------------------------------------------------------

class Championship(Base):
    __tablename__ = "championships"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(150), nullable=False)
    sport_id     = Column(Integer, ForeignKey("sports.id", ondelete="RESTRICT"), nullable=False, index=True)
    format       = Column(ChampionshipFormat, nullable=False)
    status       = Column(ChampionshipStatus, nullable=False, default="draft")
    rules_config = Column(JSON, nullable=False, default=dict,
                          comment="Critérios de classificação: pontos por vitória/empate, saldo de gols, etc.")
    extra_data   = Column(JSON, nullable=True,
                          comment="Dados adicionais livres por modalidade (ex: número de sets, tempo de jogo)")
    created_by         = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    start_date         = Column(DateTime(timezone=True))
    end_date           = Column(DateTime(timezone=True))
    current_phase         = Column(String(50), default="groups")
    group_count           = Column(Integer, nullable=True)
    group_phase_format    = Column(String(20), default="round_robin")
    teams_per_group       = Column(Integer, nullable=True)
    classifieds_per_group = Column(Integer, nullable=True, default=2)
    knockout_bracket      = Column(JSON, nullable=True,
                                   comment="Cruzamentos do mata-mata definidos manualmente")
    game_type             = Column(String(20), nullable=True,
                                   comment="Subcategoria de tabuleiro: domino, dama, xadrez")

    # relationships
    sport   = relationship("Sport", back_populates="championships")
    creator = relationship("User",  back_populates="championships_created", foreign_keys=[created_by])

    team_links           = relationship("ChampionshipTeam",      back_populates="championship", cascade="all, delete-orphan")
    games                = relationship("Game",                   back_populates="championship", cascade="all, delete-orphan")
    suspensions          = relationship("Suspension",             back_populates="championship", cascade="all, delete-orphan")
    race_results         = relationship("RaceResult",             back_populates="championship", cascade="all, delete-orphan")
    domino_teams         = relationship("DominoTeam",             back_populates="championship", cascade="all, delete-orphan")
    boardgame_participants = relationship("BoardgameParticipant", back_populates="championship", cascade="all, delete-orphan")
    boardgame_games      = relationship("BoardgameGame",          back_populates="championship", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_championships_sport_id",   "sport_id"),
        Index("ix_championships_created_by", "created_by"),
        Index("ix_championships_status",     "status"),
    )


# ---------------------------------------------------------------------------
# ChampionshipTeam  (associação N:N)
# ---------------------------------------------------------------------------

class ChampionshipTeam(Base):
    __tablename__ = "championship_teams"

    id                = Column(Integer, primary_key=True)
    championship_id   = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    team_id           = Column(Integer, ForeignKey("teams.id",         ondelete="CASCADE"), nullable=False, index=True)

    # relationships
    championship = relationship("Championship", back_populates="team_links")
    team         = relationship("Team",         back_populates="championship_links")

    __table_args__ = (
        # evita duplicatas
        Index("uq_championship_team", "championship_id", "team_id", unique=True),
    )


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class Game(Base):
    __tablename__ = "games"

    id               = Column(Integer, primary_key=True)
    championship_id  = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    home_team_id     = Column(Integer, ForeignKey("teams.id",         ondelete="RESTRICT"), nullable=False, index=True)
    away_team_id     = Column(Integer, ForeignKey("teams.id",         ondelete="RESTRICT"), nullable=False, index=True)
    scheduled_at     = Column(DateTime(timezone=True), nullable=False)
    venue            = Column(String(200))
    status           = Column(GameStatus, nullable=False, default="scheduled")
    phase            = Column(String(50),  comment="Ex: grupos, quartas, semifinal, final")
    round_number     = Column(Integer,     comment="Número da rodada dentro da fase")
    extra_data       = Column(JSON, nullable=True,
                              comment="Dados extras por modalidade (ex: sets de vôlei, parciais de basquete)")

    # relationships
    championship = relationship("Championship", back_populates="games")
    home_team    = relationship("Team", foreign_keys=[home_team_id])
    away_team    = relationship("Team", foreign_keys=[away_team_id])
    result       = relationship("GameResult", back_populates="game", uselist=False, cascade="all, delete-orphan")
    events       = relationship("GameEvent",  back_populates="game",               cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_games_championship_id", "championship_id"),
        Index("ix_games_home_team_id",    "home_team_id"),
        Index("ix_games_away_team_id",    "away_team_id"),
        Index("ix_games_status",          "status"),
        Index("ix_games_scheduled_at",    "scheduled_at"),
    )


# ---------------------------------------------------------------------------
# GameResult
# ---------------------------------------------------------------------------

class GameResult(Base):
    __tablename__ = "game_results"

    id         = Column(Integer, primary_key=True)
    game_id    = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    home_score = Column(Integer, nullable=False, default=0)
    away_score = Column(Integer, nullable=False, default=0)
    notes      = Column(Text, comment="Observações: W.O., prorrogação, etc.")
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # relationships
    game    = relationship("Game", back_populates="result")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    @property
    def created_by_name(self):
        return self.creator.name if self.creator else None

    @property
    def updated_by_name(self):
        return self.updater.name if self.updater else None


# ---------------------------------------------------------------------------
# GameEvent
# ---------------------------------------------------------------------------

class GameEvent(Base):
    __tablename__ = "game_events"

    id          = Column(Integer, primary_key=True)
    game_id     = Column(Integer, ForeignKey("games.id",    ondelete="CASCADE"),  nullable=False, index=True)
    athlete_id  = Column(Integer, ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True,  index=True)
    team_id     = Column(Integer, ForeignKey("teams.id",    ondelete="SET NULL"), nullable=True,  index=True)
    event_type  = Column(GameEventType, nullable=False)
    minute      = Column(Integer, comment="Minuto ou momento do evento")
    description = Column(String(300))
    created_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # relationships
    game    = relationship("Game",    back_populates="events")
    athlete = relationship("Athlete", back_populates="game_events")
    team    = relationship("Team",    foreign_keys=[team_id])
    creator = relationship("User",    foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_game_events_game_id",    "game_id"),
        Index("ix_game_events_athlete_id", "athlete_id"),
        Index("ix_game_events_team_id",    "team_id"),
        Index("ix_game_events_type",       "event_type"),
    )


# ---------------------------------------------------------------------------
# Suspension
# ---------------------------------------------------------------------------

class Suspension(Base):
    __tablename__ = "suspensions"

    id               = Column(Integer, primary_key=True)
    athlete_id       = Column(Integer, ForeignKey("athletes.id",     ondelete="CASCADE"),  nullable=False, index=True)
    championship_id  = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    games_remaining  = Column(Integer, nullable=False, default=1,
                              comment="Jogos que ainda restam cumprir de suspensão")
    reason           = Column(String(300), comment="Motivo da suspensão")
    auto_generated   = Column(Boolean, nullable=False, default=False,
                              comment="True quando gerada automaticamente por acúmulo de cartões")

    # relationships
    athlete      = relationship("Athlete",      back_populates="suspensions")
    championship = relationship("Championship", back_populates="suspensions")

    __table_args__ = (
        Index("ix_suspensions_athlete_id",      "athlete_id"),
        Index("ix_suspensions_championship_id", "championship_id"),
    )


# ---------------------------------------------------------------------------
# RaceResult  (resultado individual de corrida de rua)
# ---------------------------------------------------------------------------

class RaceResult(Base):
    __tablename__ = "race_results"

    id              = Column(Integer, primary_key=True)
    championship_id = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    athlete_id      = Column(Integer, ForeignKey("athletes.id",      ondelete="CASCADE"), nullable=False, index=True)
    position        = Column(Integer, nullable=True,   comment="Posição de chegada")
    finish_time     = Column(String(20), nullable=True, comment="Tempo de chegada ex: 00:45:23")
    category        = Column(String(50), nullable=True, comment="Ex: Masculino, Feminino, Master")
    bib_number      = Column(Integer, nullable=True,   comment="Número de peito")
    notes           = Column(String(300), nullable=True)
    status          = Column(String(20), nullable=False, default="registered",
                             comment="registered, finished, dnf, dsq")
    created_by      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # relationships
    championship = relationship("Championship", back_populates="race_results")
    athlete      = relationship("Athlete")
    creator      = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("uq_race_athlete", "championship_id", "athlete_id", unique=True),
        Index("ix_race_results_championship_id", "championship_id"),
    )

    @property
    def athlete_name(self):
        return self.athlete.name if self.athlete else None

    @property
    def athlete_photo_url(self):
        return self.athlete.photo_url if self.athlete else None

    @property
    def created_by_name(self):
        return self.creator.name if self.creator else None


# ---------------------------------------------------------------------------
# DominoTeam  (dupla de dominó — 2 jogadores por equipe)
# ---------------------------------------------------------------------------

class DominoTeam(Base):
    __tablename__ = "domino_teams"

    id              = Column(Integer, primary_key=True)
    championship_id = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    name            = Column(String(100), nullable=False)
    player1_id      = Column(Integer, ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True)
    player2_id      = Column(Integer, ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True)

    player1      = relationship("Athlete", foreign_keys=[player1_id])
    player2      = relationship("Athlete", foreign_keys=[player2_id])
    championship = relationship("Championship", back_populates="domino_teams")

    __table_args__ = (
        Index("ix_domino_teams_championship_id", "championship_id"),
    )


# ---------------------------------------------------------------------------
# BoardgameParticipant  (atleta inscrito em dama ou xadrez)
# ---------------------------------------------------------------------------

class BoardgameParticipant(Base):
    __tablename__ = "boardgame_participants"

    id              = Column(Integer, primary_key=True)
    championship_id = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    athlete_id      = Column(Integer, ForeignKey("athletes.id",      ondelete="CASCADE"), nullable=False, index=True)
    game_type       = Column(String(20), nullable=False, comment="dama ou xadrez")

    championship = relationship("Championship", back_populates="boardgame_participants")
    athlete      = relationship("Athlete")

    __table_args__ = (
        Index("uq_boardgame_participant", "championship_id", "athlete_id", unique=True),
    )

    @property
    def athlete_name(self):
        return self.athlete.name if self.athlete else None

    @property
    def athlete_photo_url(self):
        return self.athlete.photo_url if self.athlete else None


# ---------------------------------------------------------------------------
# BoardgameGame  (jogo de tabuleiro — dominó, dama ou xadrez)
# ---------------------------------------------------------------------------

class BoardgameGame(Base):
    __tablename__ = "boardgame_games"

    id              = Column(Integer, primary_key=True)
    championship_id = Column(Integer, ForeignKey("championships.id", ondelete="CASCADE"), nullable=False, index=True)
    game_type       = Column(String(20), nullable=False, comment="domino, dama, xadrez")
    home_id         = Column(Integer, nullable=False, comment="DominoTeam.id ou Athlete.id")
    away_id         = Column(Integer, nullable=False, comment="DominoTeam.id ou Athlete.id")
    status          = Column(String(20), nullable=False, default="scheduled",
                             comment="scheduled, finished")
    phase           = Column(String(50), nullable=True, comment="groups, knockout")
    round_number    = Column(Integer, nullable=True)
    scheduled_at    = Column(DateTime(timezone=True), nullable=True)
    extra_data      = Column(JSON, nullable=True,
                             comment="Detalhes: partidas de dominó, peças de dama, resultado de xadrez")
    home_score      = Column(Integer, nullable=True, comment="Partidas ganhas (dominó) ou pontos×10 (dama/xadrez)")
    away_score      = Column(Integer, nullable=True)
    result          = Column(String(20), nullable=True, comment="home_win, away_win, draw")

    championship = relationship("Championship", back_populates="boardgame_games")

    __table_args__ = (
        Index("ix_boardgame_games_championship_id", "championship_id"),
        Index("ix_boardgame_games_game_type",       "game_type"),
    )


# ---------------------------------------------------------------------------
# Cantina
# ---------------------------------------------------------------------------

class CantinProduct(Base):
    __tablename__ = "cantin_products"

    id          = Column(Integer, primary_key=True)
    name        = Column(String(100), nullable=False)
    description = Column(String(300), nullable=True)
    price       = Column(Numeric(10, 2), nullable=False)
    category    = Column(String(50), nullable=True)
    stock       = Column(Integer, default=0)
    min_stock   = Column(Integer, default=5)
    active      = Column(Boolean, default=True)
    image_url   = Column(String(2000), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    pdv_id      = Column(Integer, default=1, nullable=False)

    order_items = relationship("CantinOrderItem", back_populates="product")


class CantinOrder(Base):
    __tablename__ = "cantin_orders"

    id             = Column(Integer, primary_key=True)
    order_number   = Column(Integer, nullable=False)
    status         = Column(String(20), default="pending")   # pending, paid, cancelled
    payment_method = Column(String(20), nullable=True)       # dinheiro, pix
    total          = Column(Numeric(10, 2), nullable=False, default=0)
    notes          = Column(String(300), nullable=True)
    created_by     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    refunded_at    = Column(DateTime(timezone=True), nullable=True)
    refunded_by    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    refund_reason  = Column(String(300), nullable=True)
    pdv_id         = Column(Integer, default=1, nullable=False)

    items = relationship("CantinOrderItem", back_populates="order", cascade="all, delete-orphan")


class CantinOrderItem(Base):
    __tablename__ = "cantin_order_items"

    id           = Column(Integer, primary_key=True)
    order_id     = Column(Integer, ForeignKey("cantin_orders.id", ondelete="CASCADE"), nullable=False)
    product_id   = Column(Integer, ForeignKey("cantin_products.id", ondelete="SET NULL"), nullable=True)
    product_name = Column(String(100), nullable=False)
    unit_price   = Column(Numeric(10, 2), nullable=False)
    quantity     = Column(Integer, nullable=False, default=1)
    subtotal     = Column(Numeric(10, 2), nullable=False)

    order   = relationship("CantinOrder", back_populates="items")
    product = relationship("CantinProduct", back_populates="order_items")


class CantinCashFlow(Base):
    __tablename__ = "cantin_cash_flow"

    id             = Column(Integer, primary_key=True)
    type           = Column(String(10), nullable=False)       # entrada, saida
    amount         = Column(Numeric(10, 2), nullable=False)
    description    = Column(String(300), nullable=False)
    payment_method = Column(String(20), nullable=True)
    created_by     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    pdv_id         = Column(Integer, default=1, nullable=False)


# ---------------------------------------------------------------------------
# Credenciamento
# ---------------------------------------------------------------------------

class Credential(Base):
    __tablename__ = "credentials"

    id               = Column(Integer, primary_key=True)

    # Dados pessoais
    full_name        = Column(String(150), nullable=False)
    birth_date       = Column(String(10), nullable=True)   # DD/MM/YYYY
    cpf              = Column(String(14), unique=True, nullable=True)  # 000.000.000-00
    phone            = Column(String(20), nullable=True)
    city             = Column(String(100), nullable=True)

    # Dados eclesiásticos
    church           = Column(String(150), nullable=True)
    pastor_name      = Column(String(150), nullable=True)
    presbytery       = Column(String(150), nullable=True)

    # Participação no evento
    modalities       = Column(JSON, nullable=True)   # lista de modalidades
    teams            = Column(JSON, nullable=True)   # lista de equipes/times

    # Status da credencial
    status           = Column(String(20), default="pending")  # pending, approved, rejected
    rejection_reason = Column(String(300), nullable=True)
    reviewed_by      = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at      = Column(DateTime(timezone=True), nullable=True)

    # QR Code e checkin
    qr_code          = Column(String(100), unique=True, nullable=True)
    checked_in       = Column(Boolean, default=False)
    checked_in_at    = Column(DateTime(timezone=True), nullable=True)
    checked_in_by    = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    wristband_type   = Column(String(20), nullable=True)  # visitante, atleta, col

    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    reviewer     = relationship("User", foreign_keys=[reviewed_by])
    checkin_user = relationship("User", foreign_keys=[checked_in_by])
