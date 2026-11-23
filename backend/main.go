package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	_ "modernc.org/sqlite"
)

type Server struct {
	db *sql.DB
}

type Fonte struct {
	ID               int     `json:"id"`
	Slug             string  `json:"slug"`
	Nome             string  `json:"nome"`
	Orgao            string  `json:"orgao"`
	URLOficial       string  `json:"url_oficial"`
	DataAtualizacao  *string `json:"data_atualizacao"`
	NotaMetodologica string  `json:"nota_metodologica"`
}

type MapaMunicipioItem struct {
	CodigoIBGE    string   `json:"codigo_ibge"`
	Nome          string   `json:"nome"`
	Mesorregiao   *string  `json:"mesorregiao"`
	Microrregiao  *string  `json:"microrregiao"`
	ValorAbsoluto *int     `json:"valor_absoluto"`
	Taxa100k      *float64 `json:"taxa_100k"`
	FonteSlug     *string  `json:"fonte_slug"`
}

type SerieItem struct {
	Ano           int      `json:"ano"`
	Tipo          string   `json:"tipo"`
	ValorAbsoluto int      `json:"valor_absoluto"`
	Taxa100k      *float64 `json:"taxa_100k"`
	FonteNome     string   `json:"fonte_nome"`
	FonteURL      string   `json:"fonte_url"`
}

type RedeApoioItem struct {
	ID         int      `json:"id"`
	CodigoIBGE string   `json:"codigo_ibge"`
	Nome       string   `json:"nome"`
	Categoria  string   `json:"categoria"`
	Endereco   *string  `json:"endereco"`
	Telefone   *string  `json:"telefone"`
	Lat        *float64 `json:"lat"`
	Lng        *float64 `json:"lng"`
}

type MunicipioDetalhe struct {
	CodigoIBGE   string          `json:"codigo_ibge"`
	Nome         string          `json:"nome"`
	Microrregiao *string         `json:"microrregiao"`
	Mesorregiao  *string         `json:"mesorregiao"`
	Populacao    *int            `json:"populacao"`
	Series       []SerieItem     `json:"series"`
	RedeApoio    []RedeApoioItem `json:"rede_apoio"`
}

func main() {
	dbPath := envOr("DB_PATH", "../data/violencia_mg.db")
	addr := envOr("ADDR", ":8080")

	dsn := dbPath + "?_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)&_pragma=foreign_keys(ON)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		log.Fatalf("erro ao abrir SQLite: %v", err)
	}
	defer db.Close()

	db.SetMaxOpenConns(1)
	if err := db.Ping(); err != nil {
		log.Fatalf("erro ao conectar no SQLite (%s): %v", dbPath, err)
	}

	s := &Server{db: db}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/health", s.handleHealth)
	mux.HandleFunc("GET /api/fontes", s.handleFontes)
	mux.HandleFunc("GET /api/mapa", s.handleMapa)
	mux.HandleFunc("GET /api/municipio/{codigo}", s.handleMunicipio)
	mux.HandleFunc("GET /api/rede-apoio", s.handleRedeApoio)

	srv := &http.Server{
		Addr:              addr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}

	go func() {
		log.Printf("API MG rodando em http://localhost%s (SQLite: %s)", addr, dbPath)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("erro no servidor HTTP: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, os.Interrupt, syscall.SIGTERM)
	<-stop

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = srv.Shutdown(ctx)
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "escopo": "MG"})
}

func (s *Server) handleFontes(w http.ResponseWriter, r *http.Request) {
	rows, err := s.db.QueryContext(r.Context(), `
		SELECT id, slug, nome, orgao, url_oficial, data_atualizacao, nota_metodologica
		FROM fontes
		ORDER BY id
	`)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao listar fontes")
		return
	}
	defer rows.Close()

	fontes := []Fonte{}
	for rows.Next() {
		var f Fonte
		if err := rows.Scan(&f.ID, &f.Slug, &f.Nome, &f.Orgao, &f.URLOficial, &f.DataAtualizacao, &f.NotaMetodologica); err != nil {
			writeError(w, http.StatusInternalServerError, "erro ao ler fontes")
			return
		}
		fontes = append(fontes, f)
	}
	writeJSON(w, http.StatusOK, fontes)
}

func (s *Server) handleMapa(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	tipo := q.Get("tipo")
	if tipo == "" {
		tipo = "feminicidio"
	}
	ano := 2025
	if rawAno := q.Get("ano"); rawAno != "" {
		parsed, err := strconv.Atoi(rawAno)
		if err != nil {
			writeError(w, http.StatusBadRequest, "parametro 'ano' invalido")
			return
		}
		ano = parsed
	}
	mesorregiao := q.Get("mesorregiao")

	query := `
		SELECT m.codigo_ibge, m.nome, m.mesorregiao, m.microrregiao,
		       i.valor_absoluto, i.taxa_100k, f.slug
		FROM municipios m
		LEFT JOIN indicadores i
		       ON i.codigo_ibge = m.codigo_ibge AND i.ano = ? AND i.tipo = ?
		LEFT JOIN fontes f
		       ON f.id = i.fonte_id
	`
	args := []any{ano, tipo}
	if mesorregiao != "" {
		query += " WHERE m.mesorregiao = ?"
		args = append(args, mesorregiao)
	}
	query += " ORDER BY m.nome"

	rows, err := s.db.QueryContext(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao consultar mapa de MG")
		return
	}
	defer rows.Close()

	itens := []MapaMunicipioItem{}
	for rows.Next() {
		var item MapaMunicipioItem
		if err := rows.Scan(&item.CodigoIBGE, &item.Nome, &item.Mesorregiao, &item.Microrregiao, &item.ValorAbsoluto, &item.Taxa100k, &item.FonteSlug); err != nil {
			writeError(w, http.StatusInternalServerError, "erro ao ler dados municipais")
			return
		}
		itens = append(itens, item)
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"uf":    "MG",
		"ano":   ano,
		"tipo":  tipo,
		"itens": itens,
	})
}

func (s *Server) handleMunicipio(w http.ResponseWriter, r *http.Request) {
	codigo := r.PathValue("codigo")
	var d MunicipioDetalhe
	err := s.db.QueryRowContext(r.Context(), `
		SELECT codigo_ibge, nome, microrregiao, mesorregiao, populacao
		FROM municipios
		WHERE codigo_ibge = ?
	`, codigo).Scan(&d.CodigoIBGE, &d.Nome, &d.Microrregiao, &d.Mesorregiao, &d.Populacao)
	if errors.Is(err, sql.ErrNoRows) {
		writeError(w, http.StatusNotFound, "municipio nao encontrado")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao consultar municipio")
		return
	}

	sRows, err := s.db.QueryContext(r.Context(), `
		SELECT i.ano, i.tipo, i.valor_absoluto, i.taxa_100k, f.nome, f.url_oficial
		FROM indicadores i
		JOIN fontes f ON f.id = i.fonte_id
		WHERE i.codigo_ibge = ?
		ORDER BY i.ano DESC, i.tipo ASC
	`, codigo)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao consultar series historicas")
		return
	}
	defer sRows.Close()

	d.Series = []SerieItem{}
	for sRows.Next() {
		var sItem SerieItem
		if err := sRows.Scan(&sItem.Ano, &sItem.Tipo, &sItem.ValorAbsoluto, &sItem.Taxa100k, &sItem.FonteNome, &sItem.FonteURL); err != nil {
			writeError(w, http.StatusInternalServerError, "erro ao ler series historicas")
			return
		}
		d.Series = append(d.Series, sItem)
	}

	rRows, err := s.db.QueryContext(r.Context(), `
		SELECT id, codigo_ibge, nome, categoria, endereco, telefone, lat, lng
		FROM rede_apoio
		WHERE codigo_ibge = ?
		ORDER BY nome
	`, codigo)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao consultar rede de apoio")
		return
	}
	defer rRows.Close()

	d.RedeApoio = []RedeApoioItem{}
	for rRows.Next() {
		var rItem RedeApoioItem
		if err := rRows.Scan(&rItem.ID, &rItem.CodigoIBGE, &rItem.Nome, &rItem.Categoria, &rItem.Endereco, &rItem.Telefone, &rItem.Lat, &rItem.Lng); err != nil {
			writeError(w, http.StatusInternalServerError, "erro ao ler rede de apoio")
			return
		}
		d.RedeApoio = append(d.RedeApoio, rItem)
	}

	writeJSON(w, http.StatusOK, d)
}

func (s *Server) handleRedeApoio(w http.ResponseWriter, r *http.Request) {
	codigo := r.URL.Query().Get("municipio")
	query := `
		SELECT id, codigo_ibge, nome, categoria, endereco, telefone, lat, lng
		FROM rede_apoio
	`
	args := []any{}
	if codigo != "" {
		query += " WHERE codigo_ibge = ?"
		args = append(args, codigo)
	}
	query += " ORDER BY nome"

	rows, err := s.db.QueryContext(r.Context(), query, args...)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "erro ao consultar rede de apoio")
		return
	}
	defer rows.Close()

	itens := []RedeApoioItem{}
	for rows.Next() {
		var item RedeApoioItem
		if err := rows.Scan(&item.ID, &item.CodigoIBGE, &item.Nome, &item.Categoria, &item.Endereco, &item.Telefone, &item.Lat, &item.Lng); err != nil {
			writeError(w, http.StatusInternalServerError, "erro ao ler rede de apoio")
			return
		}
		itens = append(itens, item)
	}
	writeJSON(w, http.StatusOK, itens)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"erro": msg})
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
