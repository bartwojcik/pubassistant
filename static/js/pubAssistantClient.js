var pubAssistantClientApp = angular.module('pubAssistantClient', ['ui.router', 'chart.js']);

pubAssistantClientApp.config(function($httpProvider, $stateProvider, $urlRouterProvider) {
  $httpProvider.defaults.xsrfCookieName = 'csrftoken';
  $httpProvider.defaults.xsrfHeaderName = 'X-CSRFToken';
  $urlRouterProvider.otherwise('/article');
  $stateProvider
    .state('paper-analyzer', {
      abstract: true,
      controller: 'ArticleCtrl',
      url: "/article",
      templateUrl: urls.articlePartial
    })
    .state('paper-analyzer.text', {
      controller: 'ArticleCtrl',
      url: '',
      templateUrl: urls.articleTextPartial
    })
    .state('paper-analyzer.articles', {
      controller: 'ArticleCtrl',
      url: "/article_results?page",
      templateUrl: urls.articleResultsPartial,
      params: {
        page: {
            value: '1',
            squash: true
        }
      }
    })
    .state('paper-analyzer.journals', {
      controller: 'ArticleCtrl',
      url: "/journal_results?page",
      templateUrl: urls.journalResultsPartial,
      params: {
        page: {
            value: '1',
            squash: true
        }
      }
    })
    .state('hype-graph', {
      controller: 'GraphCtrl',
      url: "/graph",
      templateUrl: urls.graphPartial
    })
    .state('author-search', {
      controller: 'AuthorCtrl',
      url: "/author?search&page",
      templateUrl: urls.authorPartial,
      params: {
          page: {
              value: '1',
              squash: true
          },
          search: {
              value: '',
              squash: true
          }
        }
    })
    .state('author-details', {
          controller: 'AuthorDetailsCtrl',
          url: "/author_details?id",
          templateUrl: urls.authorDetailsPartial,
          params: {
              id: {
                value: '1'
              }
          }
    });
});

pubAssistantClientApp.directive('autofocus', ['$timeout', function($timeout) {
  return {
    restrict: 'A',
    link : function($scope, $element) {
      $timeout(function() {
        $element[0].focus();
      });
    }
  }
}]);

pubAssistantClientApp.run(function ($rootScope, $state, $stateParams) {
    $rootScope.$state = $state;
    $rootScope.$stateParams = $stateParams;
});