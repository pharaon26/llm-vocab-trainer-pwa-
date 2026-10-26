import * as api from "./api.js";
import * as pageViews from "./page-views.js";
import { show, unauthorized } from "./ui.js";
import * as views from "./views.js";

function failure(error, retry) {
  if (error.status === 401) {
    unauthorized();
    return;
  }
  show(views.messageView("Не удалось загрузить данные", error.message, "Повторить", retry));
}

export async function showDictionary() {
  show(views.loadingView("Загружаем словарь…"));
  try {
    const [entries, drafts, myCards] = await Promise.all([api.dictionary(), api.drafts(), api.myCards()]);
    show(
      pageViews.dictionaryView({
        entries,
        drafts,
        myCards,
        onAdd: () => showAddTerm(),
        onOpenDraft: (draft) => showDraft(draft),
        onDeleteDraft: async (draft) => {
          if (window.confirm(`Удалить черновик «${draft.term}»?`)) {
            await api.deleteDraft(draft.id);
            showDictionary();
          }
        },
        onEditCard: (card) => showCardEditor(card),
        onDeleteCard: async (card) => {
          const text = `Удалить слово «${card.term}»? Вместе с ним удалятся ваш прогресс и история по нему.`;
          if (window.confirm(text)) {
            await api.deleteMyCard(card.id);
            showDictionary();
          }
        },
      }),
    );
  } catch (error) {
    failure(error, showDictionary);
  }
}

async function showAddTerm(state = {}) {
  try {
    const domains = await api.domains();
    show(
      pageViews.addTermView({
        domains,
        ...state,
        onCancel: showDictionary,
        onSubmit: async (term, domain) => {
          show(views.loadingView("Ищем в словаре и просим модель дополнить поля… Это может занять до минуты."));
          try {
            const result = await api.createDraft(term, domain);
            if (result.duplicate) {
              show(
                pageViews.duplicateView({
                  duplicate: result.duplicate,
                  onBack: showDictionary,
                  onEnableDeck: async () => {
                    const decks = await api.decks();
                    const ids = decks.filter((deck) => deck.selected).map((deck) => deck.id);
                    result.duplicate.decks.forEach((deck) => ids.push(deck.id));
                    await api.saveDecks([...new Set(ids)]);
                    showDictionary();
                  },
                }),
              );
            } else {
              showDraft(result.draft);
            }
          } catch (error) {
            if (error.status === 401) {
              unauthorized();
            } else {
              showAddTerm({ term, domain, error: error.message });
            }
          }
        },
      }),
    );
  } catch (error) {
    failure(error, () => showAddTerm(state));
  }
}

async function showDraft(draft, extra = {}) {
  try {
    const domains = await api.domains();
    const handlers = {
      onSave: async ({ fields, domain }) => {
        try {
          const saved = await api.updateDraft(draft.id, { fields, domain });
          showDraft(saved, { notice: "Черновик сохранен." });
        } catch (error) {
          failedStep(error, { ...draft, fields, domain });
        }
      },
      onConfirm: async ({ fields, domain }) => {
        try {
          await api.confirmDraft(draft.id, { fields, domain });
          show(views.messageView("Слово добавлено", `«${draft.term}» теперь в ваших словах и появится в повторении среди новых терминов.`, "К словарю", showDictionary));
        } catch (error) {
          failedStep(error, { ...draft, fields, domain });
        }
      },
      onDelete: async () => {
        if (window.confirm(`Удалить черновик «${draft.term}»?`)) {
          await api.deleteDraft(draft.id);
          showDictionary();
        }
      },
      onCancel: showDictionary,
    };
    const failedStep = (error, current) => {
      if (error.status === 401) {
        unauthorized();
      } else {
        showDraft({ ...current, domain: current.domain }, { error: error.message });
      }
    };
    show(pageViews.draftEditorView({ draft, domains, mode: "draft", ...handlers, ...extra }));
  } catch (error) {
    failure(error, () => showDraft(draft, extra));
  }
}

async function showCardEditor(card, extra = {}) {
  try {
    const domains = await api.domains();
    const asDraft = {
      id: card.id,
      term: card.term,
      domain: card.domain,
      audio_url: card.audio_url,
      sources: card.sources,
      general_definition: null,
      notices: [],
      fields: {
        transcription: card.transcription,
        part_of_speech: card.part_of_speech,
        definition_en: card.definition_en,
        translation_ru: card.translation_ru,
        collocations: card.collocations,
        examples: card.examples,
        common_mistakes: card.common_mistakes,
        contrast_term: card.contrast_term,
      },
    };
    show(
      pageViews.draftEditorView({
        draft: asDraft,
        domains,
        mode: "card",
        ...extra,
        onCancel: showDictionary,
        onSave: async ({ fields, domain }) => {
          try {
            await api.updateMyCard(card.id, { term: card.term, domain, ...fields, contrast_term: fields.contrast_term || null });
            showDictionary();
          } catch (error) {
            if (error.status === 401) {
              unauthorized();
            } else {
              showCardEditor({ ...card, ...fields, domain }, { error: error.message });
            }
          }
        },
      }),
    );
  } catch (error) {
    failure(error, () => showCardEditor(card, extra));
  }
}
