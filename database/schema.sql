--
-- PostgreSQL database dump
--

\restrict 0wSW9DEwdj2CZpnEIT3KBK2bak5GEZWvJeMQ77Xi3tRjVcFfWeHd7JTgFvgmrN0

-- Dumped from database version 16.10
-- Dumped by pg_dump version 16.11

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: approval_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_queue (
    id integer NOT NULL,
    event_id integer NOT NULL,
    responsible_id integer,
    status character varying(20) NOT NULL,
    comment text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_deleted boolean DEFAULT false,
    CONSTRAINT approval_queue_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'approved'::character varying, 'rejected'::character varying, 'edited'::character varying])::text[])))
);


--
-- Name: approval_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.approval_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: approval_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.approval_queue_id_seq OWNED BY public.approval_queue.id;


--
-- Name: audit_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_log (
    id integer NOT NULL,
    user_id integer,
    action character varying(50) NOT NULL,
    entity character varying(50) NOT NULL,
    entity_id integer NOT NULL,
    payload text,
    ts timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: audit_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.audit_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.audit_log_id_seq OWNED BY public.audit_log.id;


--
-- Name: contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.contacts (
    id integer NOT NULL,
    last_name character varying(100) NOT NULL,
    first_name character varying(100) NOT NULL,
    middle_name character varying(100) NOT NULL,
    gender character varying(10) NOT NULL,
    birthday date NOT NULL,
    "position" character varying(100) NOT NULL,
    company character varying(150) NOT NULL,
    tz character varying(50),
    tg_username character varying(50) NOT NULL,
    email character varying(150) NOT NULL,
    preferred_channel character varying(50) DEFAULT 'Telegram'::character varying NOT NULL,
    default_style character varying(50) NOT NULL,
    segment character varying(50),
    notes text,
    is_active boolean DEFAULT true,
    is_deleted boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    tg_chat_id bigint,
    CONSTRAINT contacts_default_style_check CHECK (((default_style)::text = ANY ((ARRAY['Business'::character varying, 'Official'::character varying, 'Friendly'::character varying])::text[]))),
    CONSTRAINT contacts_email_format_check CHECK (((email)::text ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text)),
    CONSTRAINT contacts_gender_check CHECK (((gender)::text = ANY ((ARRAY['Male'::character varying, 'Female'::character varying])::text[]))),
    CONSTRAINT contacts_preferred_channel_check CHECK (((preferred_channel)::text = ANY ((ARRAY['Telegram'::character varying, 'Email'::character varying, 'SMS'::character varying])::text[])))
);


--
-- Name: contacts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.contacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: contacts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.contacts_id_seq OWNED BY public.contacts.id;


--
-- Name: event_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.event_log (
    id integer NOT NULL,
    event_id integer NOT NULL,
    contact_id integer NOT NULL,
    user_id integer,
    status character varying(20) NOT NULL,
    sent_at timestamp without time zone,
    duration_ms integer,
    error_message text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT event_log_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'retry'::character varying, 'partial'::character varying, 'sent'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: event_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.event_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: event_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.event_log_id_seq OWNED BY public.event_log.id;


--
-- Name: events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.events (
    id integer NOT NULL,
    contact_id integer NOT NULL,
    holiday_id integer,
    date date NOT NULL,
    channel character varying(50) DEFAULT 'Telegram'::character varying NOT NULL,
    style character varying(50) NOT NULL,
    status character varying(20) NOT NULL,
    responsible_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_deleted boolean DEFAULT false,
    generation_status character varying(20),
    generation_error text,
    generation_duration_ms integer,
    generation_cache_hit boolean,
    generation_engine character varying(64),
    generated_at timestamp without time zone,
    CONSTRAINT events_channel_check CHECK (((channel)::text = ANY ((ARRAY['Telegram'::character varying, 'Email'::character varying, 'SMS'::character varying])::text[]))),
    CONSTRAINT events_generation_status_check CHECK (((generation_status IS NULL) OR ((generation_status)::text = ANY ((ARRAY['success'::character varying, 'failed'::character varying])::text[])))),
    CONSTRAINT events_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'retry'::character varying, 'partial'::character varying, 'sent'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT events_style_check CHECK (((style)::text = ANY ((ARRAY['Business'::character varying, 'Official'::character varying, 'Friendly'::character varying])::text[])))
);


--
-- Name: events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.events_id_seq OWNED BY public.events.id;


--
-- Name: holidays; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.holidays (
    id integer NOT NULL,
    name character varying(150) NOT NULL,
    date date,
    rrule character varying(300) NOT NULL,
    target_gender character varying(10),
    category character varying(50) NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_deleted boolean DEFAULT false,
    CONSTRAINT holidays_category_check CHECK (((category)::text = ANY ((ARRAY['Official'::character varying, 'Professional'::character varying, 'Corporate'::character varying, 'Personal'::character varying, 'Other'::character varying])::text[]))),
    CONSTRAINT holidays_target_gender_check CHECK (((target_gender)::text = ANY ((ARRAY['Male'::character varying, 'Female'::character varying])::text[])))
);


--
-- Name: holidays_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.holidays_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: holidays_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.holidays_id_seq OWNED BY public.holidays.id;


--
-- Name: job_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_queue (
    id integer NOT NULL,
    event_id integer NOT NULL,
    status character varying(20) NOT NULL,
    retry_count integer DEFAULT 0,
    last_retry_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_deleted boolean DEFAULT false,
    next_retry_at timestamp without time zone,
    last_error text,
    CONSTRAINT job_queue_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'retry'::character varying, 'partial'::character varying, 'sent'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: job_queue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.job_queue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: job_queue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.job_queue_id_seq OWNED BY public.job_queue.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id integer NOT NULL,
    event_id integer NOT NULL,
    template_id integer,
    rendered_text text NOT NULL,
    pdf_path character varying(300),
    used_model character varying(100),
    grammar_score integer,
    approved_by integer,
    approved_at timestamp without time zone,
    sent_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_deleted boolean DEFAULT false
);


--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: template_blacklist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.template_blacklist (
    id integer NOT NULL,
    phrase character varying(300) NOT NULL,
    category character varying(50) NOT NULL,
    note text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    is_deleted boolean DEFAULT false NOT NULL,
    CONSTRAINT template_blacklist_phrase_not_blank CHECK ((length(btrim((phrase)::text)) > 0))
);


--
-- Name: template_blacklist_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.template_blacklist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: template_blacklist_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.template_blacklist_id_seq OWNED BY public.template_blacklist.id;


--
-- Name: templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.templates (
    id integer NOT NULL,
    channel character varying(50) DEFAULT 'Telegram'::character varying NOT NULL,
    style character varying(50) NOT NULL,
    "case" character varying(50) NOT NULL,
    category character varying(50),
    language character varying(20) DEFAULT 'ru'::character varying,
    body_text text NOT NULL,
    version integer DEFAULT 1,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_deleted boolean DEFAULT false,
    target_gender character varying(20),
    CONSTRAINT templates_case_check CHECK ((("case")::text = ANY ((ARRAY['Nominative'::character varying, 'Genitive'::character varying, 'Dative'::character varying, 'Accusative'::character varying, 'Instrumental'::character varying, 'Prepositional'::character varying])::text[]))),
    CONSTRAINT templates_channel_check CHECK (((channel)::text = ANY ((ARRAY['Telegram'::character varying, 'Email'::character varying, 'SMS'::character varying])::text[]))),
    CONSTRAINT templates_style_check CHECK (((style)::text = ANY ((ARRAY['Business'::character varying, 'Official'::character varying, 'Friendly'::character varying])::text[]))),
    CONSTRAINT templates_target_gender_check CHECK (((target_gender IS NULL) OR ((target_gender)::text = ANY ((ARRAY['Male'::character varying, 'Female'::character varying])::text[]))))
);


--
-- Name: templates_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.templates_id_seq OWNED BY public.templates.id;


--
-- Name: text_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.text_cache (
    id integer NOT NULL,
    hash_key character varying(100) NOT NULL,
    generated_text text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    used_count integer DEFAULT 0,
    is_deleted boolean DEFAULT false
);


--
-- Name: text_cache_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.text_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: text_cache_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.text_cache_id_seq OWNED BY public.text_cache.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    tg_id bigint NOT NULL,
    role character varying(20) NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    is_deleted boolean DEFAULT false,
    CONSTRAINT users_role_check CHECK (((role)::text = ANY ((ARRAY['Admin'::character varying, 'Editor'::character varying, 'Viewer'::character varying])::text[])))
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: approval_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_queue ALTER COLUMN id SET DEFAULT nextval('public.approval_queue_id_seq'::regclass);


--
-- Name: audit_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log ALTER COLUMN id SET DEFAULT nextval('public.audit_log_id_seq'::regclass);


--
-- Name: contacts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contacts ALTER COLUMN id SET DEFAULT nextval('public.contacts_id_seq'::regclass);


--
-- Name: event_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_log ALTER COLUMN id SET DEFAULT nextval('public.event_log_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events ALTER COLUMN id SET DEFAULT nextval('public.events_id_seq'::regclass);


--
-- Name: holidays id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.holidays ALTER COLUMN id SET DEFAULT nextval('public.holidays_id_seq'::regclass);


--
-- Name: job_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_queue ALTER COLUMN id SET DEFAULT nextval('public.job_queue_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: template_blacklist id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.template_blacklist ALTER COLUMN id SET DEFAULT nextval('public.template_blacklist_id_seq'::regclass);


--
-- Name: templates id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.templates ALTER COLUMN id SET DEFAULT nextval('public.templates_id_seq'::regclass);


--
-- Name: text_cache id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_cache ALTER COLUMN id SET DEFAULT nextval('public.text_cache_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: approval_queue approval_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_queue
    ADD CONSTRAINT approval_queue_pkey PRIMARY KEY (id);


--
-- Name: audit_log audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (id);


--
-- Name: contacts contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT contacts_pkey PRIMARY KEY (id);


--
-- Name: contacts contacts_tg_username_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.contacts
    ADD CONSTRAINT contacts_tg_username_unique UNIQUE (tg_username);


--
-- Name: event_log event_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_log
    ADD CONSTRAINT event_log_pkey PRIMARY KEY (id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: holidays holidays_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.holidays
    ADD CONSTRAINT holidays_pkey PRIMARY KEY (id);


--
-- Name: job_queue job_queue_event_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_queue
    ADD CONSTRAINT job_queue_event_id_key UNIQUE (event_id);


--
-- Name: job_queue job_queue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_queue
    ADD CONSTRAINT job_queue_pkey PRIMARY KEY (id);


--
-- Name: messages messages_event_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_event_id_key UNIQUE (event_id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: template_blacklist template_blacklist_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.template_blacklist
    ADD CONSTRAINT template_blacklist_pkey PRIMARY KEY (id);


--
-- Name: templates templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.templates
    ADD CONSTRAINT templates_pkey PRIMARY KEY (id);


--
-- Name: text_cache text_cache_hash_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_cache
    ADD CONSTRAINT text_cache_hash_key_key UNIQUE (hash_key);


--
-- Name: text_cache text_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.text_cache
    ADD CONSTRAINT text_cache_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_tg_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_tg_id_key UNIQUE (tg_id);


--
-- Name: ix_events_generated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_generated_at ON public.events USING btree (generated_at DESC);


--
-- Name: ix_events_generation_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_events_generation_status ON public.events USING btree (generation_status);


--
-- Name: ix_template_blacklist_phrase_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_template_blacklist_phrase_normalized ON public.template_blacklist USING btree (lower(regexp_replace(btrim((phrase)::text), '\s+'::text, ' '::text, 'g'::text))) WHERE (is_deleted = false);


--
-- Name: ix_templates_lookup_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_templates_lookup_v2 ON public.templates USING btree (channel, style, category, language, target_gender, version DESC) WHERE ((is_active = true) AND (is_deleted = false));


--
-- Name: ux_approval_queue_active_event_responsible; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_approval_queue_active_event_responsible ON public.approval_queue USING btree (event_id, COALESCE(responsible_id, '-1'::integer)) WHERE ((is_deleted = false) AND ((status)::text = ANY ((ARRAY['pending'::character varying, 'edited'::character varying])::text[])));


--
-- Name: ux_contacts_tg_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ux_contacts_tg_chat_id ON public.contacts USING btree (tg_chat_id) WHERE (tg_chat_id IS NOT NULL);


--
-- Name: approval_queue approval_queue_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_queue
    ADD CONSTRAINT approval_queue_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE RESTRICT;


--
-- Name: approval_queue approval_queue_responsible_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_queue
    ADD CONSTRAINT approval_queue_responsible_id_fkey FOREIGN KEY (responsible_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: audit_log audit_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: event_log event_log_contact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_log
    ADD CONSTRAINT event_log_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES public.contacts(id) ON DELETE RESTRICT;


--
-- Name: event_log event_log_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_log
    ADD CONSTRAINT event_log_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE RESTRICT;


--
-- Name: event_log event_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.event_log
    ADD CONSTRAINT event_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: events events_contact_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_contact_id_fkey FOREIGN KEY (contact_id) REFERENCES public.contacts(id) ON DELETE RESTRICT;


--
-- Name: events events_holiday_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_holiday_id_fkey FOREIGN KEY (holiday_id) REFERENCES public.holidays(id) ON DELETE SET NULL;


--
-- Name: events events_responsible_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.events
    ADD CONSTRAINT events_responsible_id_fkey FOREIGN KEY (responsible_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: job_queue job_queue_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_queue
    ADD CONSTRAINT job_queue_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE RESTRICT;


--
-- Name: messages messages_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: messages messages_event_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(id) ON DELETE RESTRICT;


--
-- Name: messages messages_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.templates(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict 0wSW9DEwdj2CZpnEIT3KBK2bak5GEZWvJeMQ77Xi3tRjVcFfWeHd7JTgFvgmrN0

